/**
 * Debug endpoint - shows environment variables (without sensitive values)
 * GET /api/debug
 *
 * Useful for troubleshooting environment variable issues.
 *
 * Admin-only, and set/missing only — never a value. ADMIN_EMAIL used to be
 * returned verbatim here, which is exactly the value an attacker needs to
 * impersonate the admin to any check that compares against it.
 */
import { requireAdmin } from './_utils/require-admin.js';

export async function onRequestGet(context) {
  const { env } = context;

  const denial = await requireAdmin(env, context.request);
  if (denial) return denial;

  // Check which variables are set (without exposing secrets)
  const envCheck = {
    GITHUB_TOKEN: env.GITHUB_TOKEN ? '***SET***' : 'MISSING',
    GITHUB_OWNER: env.GITHUB_OWNER || 'MISSING',
    GITHUB_REPO: env.GITHUB_REPO || 'MISSING',
    DOMAIN: env.DOMAIN || 'MISSING',
    // Set/missing only. The value is an identity, not a setting.
    ADMIN_EMAIL: env.ADMIN_EMAIL ? '***SET***' : 'MISSING',
    RESEND_API_KEY: env.RESEND_API_KEY ? '***SET***' : 'MISSING',
    INFISICAL_TOKEN: env.INFISICAL_TOKEN ? '***SET***' : 'MISSING (optional)',
    INFISICAL_PROJECT_ID: env.INFISICAL_PROJECT_ID ? '***SET***' : 'MISSING (optional)',
    CF_ACCESS_CLIENT_ID: env.CF_ACCESS_CLIENT_ID ? '***SET***' : 'MISSING (optional)',
    CF_ACCESS_CLIENT_SECRET: env.CF_ACCESS_CLIENT_SECRET ? '***SET***' : 'MISSING (optional)',
    SERVER_TYPE: env.SERVER_TYPE || 'MISSING',
    SERVER_LOCATION: env.SERVER_LOCATION || 'MISSING',
  };

  // Count missing variables
  const missing = [];
  if (!env.GITHUB_TOKEN) missing.push('GITHUB_TOKEN');
  if (!env.GITHUB_OWNER) missing.push('GITHUB_OWNER');
  if (!env.GITHUB_REPO) missing.push('GITHUB_REPO');
  if (!env.DOMAIN) missing.push('DOMAIN');

  return new Response(JSON.stringify({
    status: missing.length === 0 ? 'ok' : 'error',
    environment: 'production', // Cloudflare Pages Functions always run in production context
    variables: envCheck,
    missing: missing.length > 0 ? missing : null,
    timestamp: new Date().toISOString(),
    message: missing.length === 0
      ? 'All required environment variables are set'
      : `Missing: ${missing.join(', ')}. Set them in Cloudflare Dashboard: Pages → Settings → Environment Variables`
  }, null, 2), {
    status: missing.length === 0 ? 200 : 500,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    },
  });
}
