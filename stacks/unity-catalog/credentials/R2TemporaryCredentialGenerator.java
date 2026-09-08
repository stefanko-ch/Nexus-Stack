package ch.nexusstack.unitycatalog;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.unitycatalog.server.service.credential.CredentialContext;
import io.unitycatalog.server.service.credential.aws.AwsCredentialGenerator;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import software.amazon.awssdk.services.sts.model.Credentials;

/**
 * Mints Cloudflare R2 temporary credentials for Unity Catalog.
 *
 * <p><b>Why this class has to exist.</b> Unity Catalog's per-bucket path offers two
 * built-in generators and neither works against R2:
 *
 * <ul>
 *   <li>{@code StsAwsCredentialGenerator} calls AWS STS AssumeRole. R2 has no STS.
 *   <li>{@code StaticAwsCredentialGenerator} is selected only when
 *       {@code s3.sessionToken.<i>} is set, and R2 validates that token — an invented
 *       one is refused with {@code 403 The security token included in the request is
 *       invalid}, measured against a live bucket.
 * </ul>
 *
 * <p>Returning the plain access key with <b>no</b> session token is not a way out
 * either: {@code io.unitycatalog.hadoop.internal.auth.AwsCredential} asserts one is
 * present, so the client fails with {@code IllegalArgumentException: AWS session
 * token is missing} before any request reaches R2. A real, R2-issued token is the
 * only thing that satisfies both ends.
 *
 * <p><b>The scheme</b> is Cloudflare's documented local signing, which avoids a
 * round-trip to the Cloudflare API on every vend:
 *
 * <ol>
 *   <li>Sign a JWT with HS256 using the parent secret access key.
 *   <li>The temporary secret access key is the SHA-256 hex digest of that JWT.
 *   <li>The session token is {@code base64("jwt/" + jwt)}.
 *   <li>The access key id is the parent access key id, unchanged.
 * </ol>
 *
 * <p>Verified end-to-end against the live bucket before this class was written: a
 * triple minted exactly this way completed a PUT and a GET that the parent key's
 * own credentials would also have allowed.
 *
 * <p><b>Configuration comes from the environment</b>, not from
 * {@code server.properties}, because {@code AwsCredentialVendor} instantiates this
 * class through {@code Class.forName(...).getDeclaredConstructor().newInstance()} —
 * a no-argument constructor, which gets handed no configuration at all.
 *
 * <p>A fresh token is minted on <b>every</b> call. The alternative — minting once at
 * deploy time and writing the result into a config file — expires while the stack is
 * still running, and nothing would report it.
 */
public class R2TemporaryCredentialGenerator implements AwsCredentialGenerator {

  /** Cloudflare account that owns the bucket; also the JWT subject. */
  private static final String ENV_ACCOUNT_ID = "R2_ACCOUNT_ID";

  /** Parent S3 access key id. Reused verbatim as the temporary access key id. */
  private static final String ENV_ACCESS_KEY_ID = "R2_ACCESS_KEY_ID";

  /** Parent S3 secret. The HS256 signing key — never leaves this process. */
  private static final String ENV_SECRET_ACCESS_KEY = "R2_SECRET_ACCESS_KEY";

  /** Optional. Lifetime of a minted token in seconds. */
  private static final String ENV_TTL_SECONDS = "R2_TOKEN_TTL_SECONDS";

  private static final long DEFAULT_TTL_SECONDS = 3600L;

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Base64.Encoder URL_ENCODER = Base64.getUrlEncoder().withoutPadding();

  private final String accountId;
  private final String parentAccessKeyId;
  private final byte[] parentSecretAccessKey;
  private final long ttlSeconds;

  public R2TemporaryCredentialGenerator() {
    this.accountId = require(ENV_ACCOUNT_ID);
    this.parentAccessKeyId = require(ENV_ACCESS_KEY_ID);
    this.parentSecretAccessKey = require(ENV_SECRET_ACCESS_KEY).getBytes(StandardCharsets.UTF_8);
    this.ttlSeconds = readTtl();
  }

  private static String require(String name) {
    String value = System.getenv(name);
    if (value == null || value.isEmpty()) {
      // Deliberately names only the variable, never a value: this message reaches
      // the server log, and the repository these logs belong to is public.
      throw new IllegalStateException(
          name
              + " is unset. R2TemporaryCredentialGenerator is named by"
              + " s3.credentialGenerator.<i> in server.properties and reads its"
              + " configuration from the environment; without it Unity Catalog cannot"
              + " vend access to the bucket.");
    }
    return value;
  }

  private static long readTtl() {
    String raw = System.getenv(ENV_TTL_SECONDS);
    if (raw == null || raw.isEmpty()) {
      return DEFAULT_TTL_SECONDS;
    }
    try {
      long parsed = Long.parseLong(raw.trim());
      if (parsed <= 0) {
        throw new NumberFormatException("must be positive");
      }
      return parsed;
    } catch (NumberFormatException e) {
      throw new IllegalStateException(
          ENV_TTL_SECONDS + " must be a positive whole number of seconds", e);
    }
  }

  @Override
  public Credentials generate(CredentialContext ctx) {
    String bucket = ctx.getStorageBase().toUri().getHost();
    if (bucket == null || bucket.isEmpty()) {
      throw new IllegalStateException(
          "Cannot determine the bucket from storage base " + ctx.getStorageBase());
    }

    // SELECT alone is a read; anything that can UPDATE needs write. Scoping down
    // matters because the token travels to the Spark client, which then holds
    // whatever this grants for its whole lifetime.
    boolean needsWrite = ctx.getPrivileges().contains(CredentialContext.Privilege.UPDATE);
    String scope = needsWrite ? "object-read-write" : "object-read-only";

    Instant now = Instant.now();
    Instant expiry = now.plusSeconds(ttlSeconds);
    String jwt = signJwt(bucket, scope, now, expiry);

    return Credentials.builder()
        .accessKeyId(parentAccessKeyId)
        .secretAccessKey(sha256Hex(jwt))
        .sessionToken(
            Base64.getEncoder().encodeToString(("jwt/" + jwt).getBytes(StandardCharsets.UTF_8)))
        .expiration(expiry)
        .build();
  }

  private String signJwt(String bucket, String scope, Instant issuedAt, Instant expiry) {
    ObjectNode header = MAPPER.createObjectNode();
    header.put("alg", "HS256");
    header.put("typ", "JWT");

    ObjectNode claims = MAPPER.createObjectNode();
    claims.put("bucket", bucket);
    claims.put("scope", scope);
    claims.put("sub", accountId);
    claims.put("iss", parentAccessKeyId);
    claims.put("aud", accountId + ".r2.cloudflarestorage.com");
    claims.put("iat", issuedAt.getEpochSecond());
    claims.put("exp", expiry.getEpochSecond());

    String signingInput = encodeJson(header) + "." + encodeJson(claims);
    return signingInput + "." + URL_ENCODER.encodeToString(hmacSha256(signingInput));
  }

  private static String encodeJson(ObjectNode node) {
    try {
      return URL_ENCODER.encodeToString(MAPPER.writeValueAsBytes(node));
    } catch (Exception e) {
      throw new IllegalStateException("Could not serialise the JWT segment", e);
    }
  }

  private byte[] hmacSha256(String input) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(parentSecretAccessKey, "HmacSHA256"));
      return mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
    } catch (Exception e) {
      throw new IllegalStateException("Could not sign the R2 credential JWT", e);
    }
  }

  private static String sha256Hex(String input) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(input.getBytes(StandardCharsets.UTF_8));
      StringBuilder hex = new StringBuilder(digest.length * 2);
      for (byte b : digest) {
        hex.append(Character.forDigit((b >> 4) & 0xF, 16)).append(Character.forDigit(b & 0xF, 16));
      }
      return hex.toString();
    } catch (Exception e) {
      throw new IllegalStateException("Could not derive the temporary secret access key", e);
    }
  }
}
