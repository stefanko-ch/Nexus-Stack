/**
 * Databricks Secret Sync
 *   GET  /api/databricks-sync — last-sync summary (from KV `databricks_last_sync`)
 *   POST /api/databricks-sync — read every secret from Infisical, upsert into
 *                               the Databricks `nexus` scope, delete drifted keys,
 *                               return per-key results.
 *
 * Runs entirely inside the Pages Function — no GitHub Actions dispatch, no runner
 * cold-start. Auth sources are already wired:
 *   - Infisical via INFISICAL_TOKEN / INFISICAL_PROJECT_ID / INFISICAL_URL / INFISICAL_ENV
 *     (Pages env vars, same as /api/secrets)
 *   - Databricks via env.NEXUS_KV.get('databricks_host' | 'databricks_token')
 *     (written by /api/databricks-config)
 *
 * Scope-key convention: `<folder>/<KEY>` (e.g. `postgres/POSTGRES_USERNAME`).
 * Notebook references need to switch away from the legacy tofu-era flat keys
 * (`grafana_admin_password` → `grafana/GRAFANA_PASSWORD`); the first post-fix
 * sync removes the flat keys as drift so the scope doesn't carry both forever.
 */

import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { safeHttpsUrl } from './_utils/url.js';
import { logApiCall, logError } from './_utils/logger.js';
import { fetchAllInfisicalSecrets } from './_utils/infisical.js';
import { requireAdmin } from './_utils/require-admin.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';

const SCOPE_NAME = 'nexus';
const UPSERT_BATCH = 10;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function readDatabricksAuth(env) {
  if (!env.NEXUS_KV) return { error: 'KV not configured' };
  const hostRaw = await env.NEXUS_KV.get('databricks_host');
  const token = await env.NEXUS_KV.get('databricks_token');
  if (!hostRaw || !token) {
    return { error: 'Databricks not configured. Save host and token first.' };
  }
  const host = safeHttpsUrl(hostRaw, null);
  if (!host) {
    return { error: 'Stored databricks_host is not a valid https URL.' };
  }
  return { host, token };
}

// Databricks application-level failures can arrive either as non-200 status
// codes with an { error_code, message } body, or — for some endpoints — as
// 200 with the same error body. Centralise the success gate here so every
// call site treats both as a failure.
async function databricksCall(host, token, path, bodyObj) {
  const res = await fetchWithTimeout(`${host}${path}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(bodyObj),
  });
  let payload = null;
  try { payload = await res.json(); } catch { /* non-JSON — payload stays null */ }
  const errorCode = payload && payload.error_code;
  const ok = res.status === 200 && !errorCode;
  const error = errorCode
    ? `${errorCode}${payload.message ? `: ${payload.message}` : ''}`
    : (payload && payload.message) || null;
  return { ok, status: res.status, payload, errorCode, error };
}

async function ensureScope(host, token) {
  const result = await databricksCall(host, token, '/api/2.0/secrets/scopes/create', {
    scope: SCOPE_NAME,
    initial_manage_principal: 'users',
  });
  if (result.ok) return;
  // RESOURCE_ALREADY_EXISTS is the expected error on re-run
  if (result.errorCode === 'RESOURCE_ALREADY_EXISTS') return;
  throw new Error(`Scope create failed (${result.status}): ${result.error || 'unknown error'}`);
}

async function listScopeKeys(host, token) {
  // /secrets/list is GET-with-query in the public docs but POST also works and
  // keeps parity with the other calls; use GET to minimise surface.
  const res = await fetchWithTimeout(
    `${host}/api/2.0/secrets/list?scope=${encodeURIComponent(SCOPE_NAME)}`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  if (res.status === 404) return []; // scope exists but empty
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Scope list failed (${res.status}): ${text.substring(0, 200)}`);
  }
  const data = await res.json();
  return (data.secrets || []).map(s => s.key);
}

async function runInBatches(items, batchSize, worker) {
  const results = [];
  for (let i = 0; i < items.length; i += batchSize) {
    const chunk = items.slice(i, i + batchSize);
    const chunkResults = await Promise.all(chunk.map(worker));
    results.push(...chunkResults);
  }
  return results;
}

async function saveLastSync(env, payload) {
  if (!env.NEXUS_KV) return;
  try {
    await env.NEXUS_KV.put('databricks_last_sync', JSON.stringify(payload));
  } catch (err) {
    // Best-effort — the sync itself already succeeded/failed and returned.
    console.error('Failed to persist databricks_last_sync to KV:', err);
  }
}

export async function onRequestGet(context) {
  const { env } = context;
  if (!env.NEXUS_KV) {
    return jsonResponse({ success: true, status: 'never', message: 'No sync has been run yet' });
  }
  try {
    const raw = await env.NEXUS_KV.get('databricks_last_sync');
    if (!raw) {
      return jsonResponse({ success: true, status: 'never', message: 'No sync has been run yet' });
    }
    const last = JSON.parse(raw);
    return jsonResponse({ success: true, ...last });
  } catch {
    return jsonResponse({ success: true, status: 'unknown', message: 'Could not read last-sync status' });
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

  const auth = await readDatabricksAuth(env);
  if (auth.error) {
    return jsonResponse({ success: false, error: auth.error }, 400);
  }
  const { host, token } = auth;

  await logApiCall(env.NEXUS_DB, '/api/databricks-sync', 'POST', {
    action: 'databricks_sync_start',
    host,
  });

  // 1. Pull every secret from Infisical via the shared helper
  let inventory;
  try {
    inventory = await fetchAllInfisicalSecrets(env);
  } catch (err) {
    await logError(env.NEXUS_DB, '/api/databricks-sync', 'Infisical fetch failed', err);
    const payload = {
      status: 'failure',
      timestamp: new Date().toISOString(),
      message: `Failed to read from Infisical: ${err.message}`,
      upserted: 0, deleted: 0, failed: [],
    };
    await saveLastSync(env, payload);
    return jsonResponse({ success: false, ...payload }, 502);
  }

  if (!inventory.configured) {
    return jsonResponse({ success: false, error: inventory.message }, 400);
  }

  // Flatten groups → [{ scopeKey, value }]
  const desired = [];
  for (const group of inventory.groups) {
    for (const secret of group.secrets) {
      desired.push({ scopeKey: `${group.name}/${secret.key}`, value: secret.value });
    }
  }
  const desiredKeys = new Set(desired.map(d => d.scopeKey));

  // 2. Make sure the scope exists
  try {
    await ensureScope(host, token);
  } catch (err) {
    await logError(env.NEXUS_DB, '/api/databricks-sync', 'Scope create failed', err);
    const payload = {
      status: 'failure',
      timestamp: new Date().toISOString(),
      message: err.message,
      upserted: 0, deleted: 0, failed: [],
    };
    await saveLastSync(env, payload);
    return jsonResponse({ success: false, ...payload }, 502);
  }

  // 3. Diff against current scope contents → list of stale keys to delete
  let existingKeys = [];
  let driftCleanupSkipped = false;
  try {
    existingKeys = await listScopeKeys(host, token);
  } catch (err) {
    // Non-fatal: continue with upserts, but flag the run as partial — the
    // "strict mirror" guarantee doesn't hold if we didn't check for drift.
    driftCleanupSkipped = true;
    inventory.warnings = inventory.warnings || [];
    inventory.warnings.push(`Scope list failed; stale keys were not checked or removed this run: ${err.message}`);
  }
  const stale = existingKeys.filter(k => !desiredKeys.has(k));

  // 4. Upsert desired keys + delete stale keys in parallel batches
  const failed = [];

  const upsertResults = await runInBatches(desired, UPSERT_BATCH, async ({ scopeKey, value }) => {
    try {
      const result = await databricksCall(host, token, '/api/2.0/secrets/put', {
        scope: SCOPE_NAME,
        key: scopeKey,
        string_value: value,
      });
      if (!result.ok) {
        return { ok: false, key: scopeKey, error: `HTTP ${result.status}: ${result.error || 'put failed'}` };
      }
      return { ok: true };
    } catch (err) {
      return { ok: false, key: scopeKey, error: err.message };
    }
  });
  upsertResults.filter(r => !r.ok).forEach(r => failed.push({ key: r.key, error: r.error }));

  const deleteResults = await runInBatches(stale, UPSERT_BATCH, async (scopeKey) => {
    try {
      const result = await databricksCall(host, token, '/api/2.0/secrets/delete', {
        scope: SCOPE_NAME,
        key: scopeKey,
      });
      if (!result.ok) {
        return { ok: false, key: scopeKey, error: `HTTP ${result.status}: ${result.error || 'delete failed'}` };
      }
      return { ok: true };
    } catch (err) {
      return { ok: false, key: scopeKey, error: err.message };
    }
  });
  deleteResults.filter(r => !r.ok).forEach(r => failed.push({ key: r.key, error: `delete: ${r.error}` }));

  const upserted = upsertResults.filter(r => r.ok).length;
  const deleted = deleteResults.filter(r => r.ok).length;
  // Any warning (drift-skip, Infisical folder fetch failure, …) means the
  // scope isn't a guaranteed mirror this run — surface that as `partial`
  // alongside per-key failures, so the UI never shows a green "success"
  // when some secrets were silently skipped.
  const hasWarnings = (inventory.warnings || []).length > 0;
  const status = (failed.length === 0 && !hasWarnings) ? 'success' : 'partial';
  const timestamp = new Date().toISOString();
  const parts = [`Synced ${upserted} secrets`];
  if (driftCleanupSkipped) {
    parts.push('drift cleanup skipped');
  } else {
    parts.push(`removed ${deleted} stale entries`);
  }
  if (failed.length > 0) parts.push(`${failed.length} failed`);
  const message = parts.join(', ') + '.';

  const result = {
    status,
    timestamp,
    message,
    upserted,
    deleted,
    failed,
    warnings: inventory.warnings || [],
  };

  await saveLastSync(env, result);
  await logApiCall(env.NEXUS_DB, '/api/databricks-sync', 'POST', {
    action: 'databricks_sync_complete',
    status, upserted, deleted, failed_count: failed.length,
  });

  // `success` tracks the computed `status` — a partial run (drift-skip,
  // Infisical fetch warnings, or per-key failures) is not a success, even
  // if every upsert attempt returned 200.
  return jsonResponse({ success: status === 'success', ...result });
}
