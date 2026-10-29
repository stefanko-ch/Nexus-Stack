/**
 * Trigger Setup Control Plane workflow
 * POST /api/setup
 *
 * Triggers the GitHub Actions setup-control-plane.yaml workflow.
 * Includes validation, error handling, and retry logic.
 */
import { dispatchWorkflow, forgeErrorMessage, forgeErrorStatus } from './_utils/forge.js';
import { logApiCall, logError } from './_utils/logger.js';
import { requireAdmin } from './_utils/require-admin.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';
import { markDispatched } from './_utils/dispatch-marker.js';

export async function onRequestPost(context) {
  const { env, request } = context;
  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const denial = await requireAdmin(env, request);
  if (denial) return denial;

  // Validate environment variables
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Missing required environment variables'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const response = await dispatchWorkflow(env, 'setup-control-plane.yaml');

    if (response.status === 204) {
      const tracked = await markDispatched(env.NEXUS_DB, 'setup');
      await logApiCall(env.NEXUS_DB, '/api/setup', 'POST', {
        action: 'setup_control_plane_triggered',
      });
      return new Response(JSON.stringify({
        success: true,
        tracked,
        message: 'Setup workflow triggered successfully'
      }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
        },
      });
    }

    const errorMessage = await forgeErrorMessage(response, 'Failed to trigger workflow');

    console.error(`Setup trigger failed: ${response.status} - ${errorMessage}`);

    return new Response(JSON.stringify({
      success: false,
      error: errorMessage
    }), {
      status: forgeErrorStatus(response),
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Setup endpoint error:', error);
    await logError(env.NEXUS_DB, '/api/setup', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Network error while triggering workflow'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
