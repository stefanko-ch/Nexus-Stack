/**
 * Databricks Configuration API
 * GET /api/databricks-config - Get current configuration (host only, never return token)
 * POST /api/databricks-config - Save host + token to Cloudflare KV
 *
 * Credentials persist in KV across normal stack teardown (unlike D1)
 */

import { logApiCall, logError } from './_utils/logger.js';
import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { requireAdmin } from './_utils/require-admin.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';

export async function onRequestGet(context) {
  const { env } = context;

  try {
    if (!env.NEXUS_KV) {
      return new Response(JSON.stringify({ success: false, error: 'KV not configured' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const host = await env.NEXUS_KV.get('databricks_host') || '';
    const hasToken = !!(await env.NEXUS_KV.get('databricks_token'));

    return new Response(JSON.stringify({
      success: true,
      configured: !!(host && hasToken),
      host,
      hasToken,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    await logError(env.NEXUS_DB, '/api/databricks-config', 'Failed to read config', error);
    return new Response(JSON.stringify({ success: false, error: 'Failed to read config' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

export async function onRequestPost(context) {
  const { env, request } = context;
  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const denial = requireAdmin(env, request);
  if (denial) return denial;

  try {
    if (!env.NEXUS_KV) {
      return new Response(JSON.stringify({ success: false, error: 'KV not configured' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const body = await request.json();
    const host = typeof body.host === 'string' ? body.host.trim().replace(/\/+$/, '') : '';
    const token = typeof body.token === 'string' ? body.token.trim() : '';

    if (!host || !token) {
      return new Response(JSON.stringify({ success: false, error: 'Both host and token are required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (!host.startsWith('https://')) {
      return new Response(JSON.stringify({ success: false, error: 'Host must start with https://' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Test connection before saving
    try {
      const testRes = await fetchWithTimeout(`${host}/api/2.0/clusters/list`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (testRes.status === 401) {
        return new Response(JSON.stringify({ success: false, error: 'Invalid or expired token (401)' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (testRes.status === 403) {
        // 403 = token valid but lacks permissions — still save since token works
        // (user may have restricted RBAC but secrets API could still work)
      } else if (!testRes.ok) {
        return new Response(JSON.stringify({ success: false, error: `Connection failed (HTTP ${testRes.status})` }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    } catch (err) {
      return new Response(JSON.stringify({ success: false, error: `Cannot reach ${host} — check the URL` }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    await env.NEXUS_KV.put('databricks_host', host);
    await env.NEXUS_KV.put('databricks_token', token);

    await logApiCall(env.NEXUS_DB, '/api/databricks-config', 'POST', {
      action: 'save_databricks_config',
      host,
    });

    return new Response(JSON.stringify({ success: true, message: 'Connection verified and configuration saved' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    await logError(env.NEXUS_DB, '/api/databricks-config', 'Failed to save config', error);
    return new Response(JSON.stringify({ success: false, error: 'Failed to save config' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
