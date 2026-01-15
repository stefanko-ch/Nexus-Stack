/**
 * Health check endpoint
 * GET /api/health
 * 
 * Simple health check to verify the API is working.
 * Does not require GitHub token (for basic connectivity checks).
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
