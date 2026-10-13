// Identify the caller from a verified Cloudflare Access token.
//
// This used to read `Cf-Access-Authenticated-User-Email`, or base64-decode
// the JWT payload without checking the signature. Both are only as good as
// the assumption that every route reaching this code passed through
// Access — an assumption about infrastructure, held outside this
// repository, and one this project destroys and recreates routinely.
//
// Now the token is verified: signature against the Access JWKS, plus
// `iss`, `aud` and `exp`. See `access-jwt.js`.
//
// `getAccessUserEmail` is async as a result. Every caller awaits it.
import { verifyAccessJwt, AccessJwtError } from './access-jwt.js';

/**
 * The verified caller's email, or null.
 *
 * Returns null — never a fallback identity — when the token is missing,
 * malformed, expired, or signed by someone else. The guards that call this
 * treat null as "deny", so a configuration mistake locks people out rather
 * than letting an unverified header through. That is the direction to fail
 * in: a locked-out operator notices within seconds, a trusted header does
 * not.
 *
 * @returns {Promise<{ email: string | null, reason: string | null }>}
 *   `reason` is a short, token-free string for the caller to surface when
 *   the deployment is misconfigured, so a 403 can say which secret is
 *   missing instead of looking like a permissions problem.
 */
export async function getAccessUserEmail(request, env, options = {}) {
  const token = request.headers.get('Cf-Access-Jwt-Assertion');

  try {
    const payload = await verifyAccessJwt(token, {
      teamDomain: env.ACCESS_TEAM_DOMAIN,
      aud: env.ACCESS_AUD,
      ...options,
    });
    const email = typeof payload.email === 'string' ? payload.email.trim() : '';
    return { email: email || null, reason: email ? null : 'token carries no email claim' };
  } catch (err) {
    if (err instanceof AccessJwtError) return { email: null, reason: err.reason };
    return { email: null, reason: `verification failed (${err?.name || 'Error'})` };
  }
}
