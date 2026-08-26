/**
 * Trigger Spin-Up workflow
 * POST /api/spin-up
 *
 * Triggers the configured spin-up workflow — spin-up.yml or
 * spin-up-snapshot.yml, selected by config.lifecycle_mode in D1.
 * Reads enabled services from D1 (single source of truth).
 */

import { logApiCall, logError } from './_utils/logger.js';
import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { resolveLifecycle } from './_utils/workflow-selection.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';

/**
 * Get enabled services from D1
 * Returns list of service names where enabled = true
 */
async function getEnabledServicesFromD1(db) {
  try {
    const results = await db.prepare(
      'SELECT name FROM services WHERE enabled = 1'
    ).all();
    return (results.results || []).map(row => row.name);
  } catch {
    return [];
  }
}

export async function onRequestPost(context) {
  const { env, request } = context;

  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

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
    // Get enabled services from D1 (single source of truth)
    let enabledServicesList = [];

    if (env.NEXUS_DB) {
      enabledServicesList = await getEnabledServicesFromD1(env.NEXUS_DB);
    }

    // Log the spin-up request
    await logApiCall(env.NEXUS_DB, '/api/spin-up', 'POST', {
      action: 'trigger_spin_up',
      enabledServices: enabledServicesList,
      serviceCount: enabledServicesList.length,
    });

    // See teardown.js. Less destructive on this side — a wrong spin-up
    // wastes an image rather than destroying one — but guessing the mode
    // would still start the wrong half of a pair.
    const lifecycle = await resolveLifecycle(env.NEXUS_DB);
    if (!lifecycle.ok) {
      return new Response(JSON.stringify({
        success: false,
        error: `Cannot determine the lifecycle mode (${lifecycle.reason}) — refusing to dispatch a spin-up`,
      }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${lifecycle.spinUp}/dispatches`;

    const response = await fetchWithTimeout(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Plane',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: {
          enabled_services: enabledServicesList.join(',')
        }
      }),
    });

    if (response.status === 204) {
      return new Response(JSON.stringify({
        success: true,
        message: 'Spin-up workflow triggered successfully',
        enabledServices: enabledServicesList
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const errorText = await response.text();
    let errorMessage = `Failed to trigger workflow: ${response.status}`;

    try {
      const errorJson = JSON.parse(errorText);
      errorMessage = errorJson.message || errorMessage;
    } catch {
      if (errorText) {
        errorMessage = errorText.substring(0, 200);
      }
    }

    console.error(`Spin-up trigger failed: ${response.status} - ${errorMessage}`);
    await logError(env.NEXUS_DB, '/api/spin-up', 'POST', new Error(errorMessage));

    return new Response(JSON.stringify({
      success: false,
      error: errorMessage
    }), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Spin-up endpoint error:', error);
    await logError(env.NEXUS_DB, '/api/spin-up', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Network error while triggering workflow'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
