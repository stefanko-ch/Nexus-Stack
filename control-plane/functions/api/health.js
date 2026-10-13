/**
 * Health check endpoint
 * GET /api/health
 *
 * Simple health check to verify the API is working.
 * Does not require GitHub token (for basic connectivity checks).
 *
 * Deliberately NOT identity-guarded: the response is a fixed string, a
 * timestamp and a hardcoded "1.0.0" — no deployment state at all — and an
 * uptime check has no Access token to present. The hostname check in
 * functions/_middleware.js still applies, so this answers on the Control
 * Plane's own hostname and nowhere else.
 */
export async function onRequestGet() {
  return new Response(JSON.stringify({
    status: 'ok',
    service: 'Nexus-Stack Control Plane API',
    timestamp: new Date().toISOString(),
    version: '1.0.0'
  }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    },
  });
}
