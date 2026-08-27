/**
 * Trigger Teardown workflow
 * POST /api/teardown
 *
 * Triggers the configured teardown workflow — teardown.yml or
 * teardown-snapshot.yml, selected by config.lifecycle_mode in D1.
 * Includes validation and error handling.
 */

import { logApiCall, logError } from './_utils/logger.js';
import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { requireOperator } from './_utils/require-operator.js';
import { resolveLifecycle } from './_utils/workflow-selection.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';

export async function onRequestPost(context) {
  const { env, request } = context;
  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  // Operator-level, not admin-only. Users must be able to stop the stack
  // they can start — the asymmetry this replaces let a student begin
  // paying for a server and then wait for somebody else to release it.
  // Guests still cannot: tearing down a stack somebody is working on is
  // not a spectator's call.
  const denial = requireOperator(env, request);
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
  await logApiCall(env.NEXUS_DB, '/api/teardown', 'POST', {
    action: 'trigger_teardown',
    source: 'control-plane-ui',
  });

  // Refuse rather than guess. If the lifecycle mode cannot be determined
  // we do not know whether this stack is on snapshots, and defaulting to
  // the rebuild pair would run an untargeted `tofu destroy` that rotates
  // every generated credential and orphans any existing snapshot.
  // An UNCONFIGURED stack is a different case and resolves fine.
  const lifecycle = await resolveLifecycle(env.NEXUS_DB);
  if (!lifecycle.ok) {
    return new Response(JSON.stringify({
      success: false,
      error: `Cannot determine the lifecycle mode (${lifecycle.reason}) — refusing to dispatch a teardown`,
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${lifecycle.teardown}/dispatches`;

  try {
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
          confirm: 'TEARDOWN'
        }
      }),
    });

    if (response.status === 204) {
      return new Response(JSON.stringify({
        success: true,
        message: 'Teardown workflow triggered successfully'
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

    console.error(`Teardown trigger failed: ${response.status} - ${errorMessage}`);

    return new Response(JSON.stringify({
      success: false,
      error: errorMessage
    }), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Teardown endpoint error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Network error while triggering workflow'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
