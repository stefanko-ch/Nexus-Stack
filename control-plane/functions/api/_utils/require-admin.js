// Authorization guard for admin-only endpoints.
//
// Cloudflare Access authenticates the caller but doesn't authorize per-role:
// every email on the Access whitelist (admin + users + guests) reaches every
// endpoint with the same rights. This helper restricts an endpoint to the
// single ADMIN_EMAIL identity by comparing it against the Access-authenticated
// caller (extracted from the JWT). Comparison is case-insensitive to match
// Cloudflare Access / identity-provider behaviour.
//
// The caller's identity comes from a VERIFIED Access token — signature,
// iss, aud and exp — so a self-set `Cf-Access-*` header no longer passes
// this guard. See cf-access-email.js and access-jwt.js.
//
// Usage at the top of any admin-only handler (note the await):
//   const denial = await requireAdmin(context.env, context.request);
//   if (denial) return denial;
import { getAccessUserEmail } from './cf-access-email.js';
import { misconfigured, forbidden } from './deny.js';

export async function requireAdmin(env, request) {
  const adminEmail = (env.ADMIN_EMAIL || '').trim().toLowerCase();
  if (!adminEmail) return misconfigured('ADMIN_EMAIL is not set');

  const { email, reason } = await getAccessUserEmail(request, env);
  const caller = (email || '').trim().toLowerCase();
  if (!caller || caller !== adminEmail) {
    return forbidden('Forbidden: this endpoint requires admin access', reason);
  }
  return null;
}
