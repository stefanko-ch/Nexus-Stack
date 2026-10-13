/**
 * Verify a Cloudflare Access JWT properly, instead of trusting it.
 *
 * Access signs an RS256 JWT and puts it in `Cf-Access-Jwt-Assertion`. The
 * previous implementation read the `Cf-Access-Authenticated-User-Email`
 * header, or base64-decoded the JWT's payload — neither checks that
 * Cloudflare actually issued the thing. That is safe only while every
 * route reaching this code has passed through Access, which is an
 * assumption about infrastructure, held outside this repository.
 *
 * What is checked here:
 *
 *   signature   RS256 against the JWKS Access publishes
 *   iss         equals https://<team>.cloudflareaccess.com
 *   aud         contains this application's AUD tag
 *   exp / nbf   with a small clock skew allowance
 *
 * The JWKS is cached per isolate. Workers isolates are short-lived and
 * numerous, so this is a hit-rate optimisation rather than a guarantee.
 *
 * A cache alone is not enough, though: Access rotates its signing keys,
 * and between a rotation and the cache expiring, a warm isolate would
 * reject perfectly valid tokens. So an unknown `kid` refetches the JWKS
 * once before rejecting — rate-limited, because `kid` comes from the
 * token and a made-up one must not buy an outbound request per attempt.
 */

/** Seconds of tolerance for exp/nbf. Access tokens live hours; this is noise. */
const CLOCK_SKEW_SECONDS = 60;

/** How long a fetched JWKS is reused inside one isolate. */
const JWKS_TTL_MS = 10 * 60 * 1000;

/**
 * Floor between two refreshes triggered by an unknown `kid`.
 *
 * Without it, a token carrying a random `kid` would cost one request to
 * Cloudflare per attempt. Shorter than JWKS_TTL_MS, because the case it
 * serves is a key rotation that must be picked up quickly; long enough
 * that a flood collapses into one fetch.
 */
const JWKS_MISS_REFRESH_MS = 60 * 1000;

/** @type {{ url: string, keys: Map<string, CryptoKey>, fetchedAt: number } | null} */
let jwksCache = null;

/** When a kid-miss last caused a refetch. Per isolate, like the cache. */
let lastMissRefreshAt = 0;

export class AccessJwtError extends Error {
  /**
   * @param {string} reason  short, safe to log — never carries token content
   */
  constructor(reason) {
    super(reason);
    this.name = 'AccessJwtError';
    this.reason = reason;
  }
}

function base64UrlToBytes(value) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function base64UrlToString(value) {
  return new TextDecoder().decode(base64UrlToBytes(value));
}

/**
 * The team domain, normalised to a bare hostname.
 *
 * Accepts `nitako`, `nitako.cloudflareaccess.com` or the full https URL,
 * because all three are things an operator reasonably pastes.
 */
export function normaliseTeamDomain(raw) {
  const value = (raw || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/+$/, '');
  if (!value) return null;
  return value.includes('.') ? value : `${value}.cloudflareaccess.com`;
}

async function fetchJwks(teamDomain, fetchImpl, { force = false } = {}) {
  const url = `https://${teamDomain}/cdn-cgi/access/certs`;
  const now = Date.now();
  if (!force && jwksCache && jwksCache.url === url && now - jwksCache.fetchedAt < JWKS_TTL_MS) {
    return jwksCache.keys;
  }

  let payload;
  try {
    const response = await fetchImpl(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new AccessJwtError(`JWKS endpoint returned HTTP ${response.status}`);
    payload = await response.json();
  } catch (err) {
    if (err instanceof AccessJwtError) throw err;
    // Never the upstream message: it can carry response text.
    throw new AccessJwtError(`JWKS fetch failed (${err?.name || 'Error'})`);
  }

  const jwks = Array.isArray(payload?.keys) ? payload.keys : null;
  if (!jwks || jwks.length === 0) throw new AccessJwtError('JWKS response had no keys');

  const keys = new Map();
  for (const jwk of jwks) {
    if (!jwk || typeof jwk.kid !== 'string') continue;
    try {
      keys.set(
        jwk.kid,
        await crypto.subtle.importKey(
          'jwk',
          { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: 'RS256', ext: true },
          { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
          false,
          ['verify'],
        ),
      );
    } catch {
      // One unusable key must not discard the rest.
    }
  }
  if (keys.size === 0) throw new AccessJwtError('JWKS held no importable RS256 keys');

  jwksCache = { url, keys, fetchedAt: now };
  return keys;
}

/** Drop the cache. Exported for tests; nothing in production calls it. */
export function _resetJwksCache() {
  jwksCache = null;
  lastMissRefreshAt = 0;
}

/**
 * The key for `kid`, refetching the JWKS once if it is not in the cache.
 *
 * The refetch is what makes a key rotation visible to a warm isolate. The
 * rate limit is what stops a forged `kid` from turning every request into
 * an outbound fetch — on a limited window, a miss is simply a rejection,
 * which is the correct answer for a `kid` that does not exist.
 */
async function keyForKid(kid, teamDomain, fetchImpl, now) {
  const cached = await fetchJwks(teamDomain, fetchImpl);
  const key = cached.get(kid);
  if (key) return key;

  const sinceLastRefresh = now() - lastMissRefreshAt;
  if (sinceLastRefresh < JWKS_MISS_REFRESH_MS) return undefined;

  // Set before the fetch, not after: a burst of misses that all arrive
  // while the first fetch is in flight must not each start one.
  lastMissRefreshAt = now();
  const refreshed = await fetchJwks(teamDomain, fetchImpl, { force: true });
  return refreshed.get(kid);
}

/**
 * Verify `token` and return its payload.
 *
 * @throws {AccessJwtError} with a `reason` that is safe to log — it never
 *   contains any part of the token.
 */
export async function verifyAccessJwt(token, { teamDomain, aud, fetchImpl = fetch, now = Date.now } = {}) {
  const team = normaliseTeamDomain(teamDomain);
  if (!team) throw new AccessJwtError('ACCESS_TEAM_DOMAIN is not set');
  if (!aud) throw new AccessJwtError('ACCESS_AUD is not set');
  if (!token) throw new AccessJwtError('no Cf-Access-Jwt-Assertion header');

  const parts = token.split('.');
  if (parts.length !== 3) throw new AccessJwtError('token is not a three-part JWT');
  const [headerPart, payloadPart, signaturePart] = parts;

  let header;
  let payload;
  try {
    header = JSON.parse(base64UrlToString(headerPart));
    payload = JSON.parse(base64UrlToString(payloadPart));
  } catch {
    throw new AccessJwtError('token header or payload is not JSON');
  }

  // Pin the algorithm. Without this, a token with `alg: none` — or any
  // algorithm whose verification we did not intend — decides for us.
  if (header?.alg !== 'RS256') throw new AccessJwtError('token alg is not RS256');
  if (typeof header?.kid !== 'string') throw new AccessJwtError('token has no kid');

  const key = await keyForKid(header.kid, team, fetchImpl, now);
  if (!key) throw new AccessJwtError('token kid is not in the JWKS');

  const verified = await crypto.subtle.verify(
    { name: 'RSASSA-PKCS1-v1_5' },
    key,
    base64UrlToBytes(signaturePart),
    new TextEncoder().encode(`${headerPart}.${payloadPart}`),
  );
  if (!verified) throw new AccessJwtError('signature does not verify');

  const expectedIss = `https://${team}`;
  if (payload?.iss !== expectedIss) throw new AccessJwtError('iss does not match the team domain');

  // `aud` is a string or an array of strings, per RFC 7519.
  const audience = Array.isArray(payload?.aud) ? payload.aud : [payload?.aud];
  if (!audience.includes(aud)) throw new AccessJwtError('aud does not include this application');

  const seconds = Math.floor(now() / 1000);
  if (typeof payload?.exp !== 'number') throw new AccessJwtError('token has no exp');
  if (payload.exp + CLOCK_SKEW_SECONDS < seconds) throw new AccessJwtError('token has expired');
  if (typeof payload?.nbf === 'number' && payload.nbf - CLOCK_SKEW_SECONDS > seconds) {
    throw new AccessJwtError('token is not valid yet');
  }

  return payload;
}
