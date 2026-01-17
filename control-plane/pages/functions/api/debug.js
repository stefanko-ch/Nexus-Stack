/**
 * Debug endpoint - shows environment variables (without sensitive values)
 * GET /api/debug
 * 
 * Useful for troubleshooting environment variable issues.
 * Does NOT expose GITHUB_TOKEN value (security).
 */
export async function onRequestGet(context) {
  const { env } = context;
  
  // Check which variables are set (without exposing secrets)
  const envCheck = {
    GITHUB_TOKEN: env.GITHUB_TOKEN ? '***SET***' : 'MISSING',
    GITHUB_OWNER: env.GITHUB_OWNER || 'MISSING',
    GITHUB_REPO: env.GITHUB_REPO || 'MISSING',
    DOMAIN: env.DOMAIN || 'MISSING',
    ADMIN_EMAIL: env.ADMIN_EMAIL || 'MISSING',
    RESEND_API_KEY: env.RESEND_API_KEY ? '***SET***' : 'MISSING',
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
