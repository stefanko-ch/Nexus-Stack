/**
 * Trigger Setup Control Plane workflow
 * POST /api/deploy (legacy endpoint name for backward compatibility)
 *
 * Triggers the GitHub Actions setup-control-plane.yaml workflow.
 * Includes validation, error handling, and retry logic.
 */

import { logApiCall, logError } from './_utils/logger.js';
import { dispatchWorkflow, forgeErrorMessage, forgeErrorStatus } from './_utils/forge.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';
import { requireAdmin } from './_utils/require-admin.js';
import { markDispatched } from './_utils/dispatch-marker.js';

export async function onRequestPost(context) {
  const { env, request } = context;

  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  // Admin-only: this redeploys the Control Plane itself via the
  // setup-control-plane workflow, which rotates its secrets and rebuilds the
  // Pages project. That is operator work, not the per-student self-service
  // that spin-up and the service toggles deliberately allow.
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

  // Log the API call
  await logApiCall(env.NEXUS_DB, '/api/deploy', 'POST', {
    action: 'trigger_setup_control_plane',
  });

  try {
    const response = await dispatchWorkflow(env, 'setup-control-plane.yaml');

    // GitHub returns 204 No Content on success
    if (response.status === 204) {
      const tracked = await markDispatched(env.NEXUS_DB, 'setup');
      return new Response(JSON.stringify({
        success: true,
        tracked,
        message: 'Deploy workflow triggered successfully'
      }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
        },
      });
    }

    // Handle errors
    const errorMessage = await forgeErrorMessage(response, 'Failed to trigger workflow');

    console.error(`Deploy trigger failed: ${response.status} - ${errorMessage}`);

    return new Response(JSON.stringify({
      success: false,
      error: errorMessage
    }), {
      status: forgeErrorStatus(response),
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Deploy endpoint error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Network error while triggering workflow'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
