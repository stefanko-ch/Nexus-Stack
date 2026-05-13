/**
 * Manage services configuration
 * GET /api/services - Get all services from D1 (single source of truth)
 * POST /api/services - Enable/disable a service (staged in D1, not deployed)
 *
 * Service metadata is synced to D1 by .github/scripts/sync-deployed-state.sh, which
 * runs at the end of the spin-up workflow. D1 column migrations (e.g. landing_path)
 * run in setup-control-plane.yaml's "Apply D1 schema" step + idempotently from the
 * sync script too — so the new Pages frontend never reads a column that doesn't
 * exist in D1 yet.
 * D1 is the single source of truth for service state:
 *   - enabled: what the user wants (staged state)
 *   - deployed: what is currently running
 */

import { logApiCall, logError } from './_utils/logger.js';

/**
 * Validate service name to prevent injection attacks
 * Only allows lowercase letters, numbers, hyphens, and underscores
 * @param {string} name - Service name to validate
 * @returns {boolean} - True if valid, false otherwise
 */
function validateServiceName(name) {
  if (typeof name !== 'string') {
    return false;
  }
  if (name.length === 0 || name.length > 63) {
    return false;
  }
  // Only allow: lowercase letters, numbers, hyphens, underscores
  // Ensure the name starts and ends with an alphanumeric character
  // This prevents issues with DNS names and file paths
  return /^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$/.test(name);
}

/**
 * GET /api/services
 * Returns all services from D1
 */
export async function onRequestGet(context) {
  const { env, request } = context;

  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured',
      services: [],
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    // Support optional category filter via query parameter
    const url = new URL(request.url);
    const categoryFilter = url.searchParams.get('category');

    let stmt;
    if (categoryFilter) {
      stmt = env.NEXUS_DB.prepare(`
        SELECT name, enabled, deployed, subdomain, port, public, core, admin_only, description, category, website, long_description, landing_path
        FROM services
        WHERE category = ?
        ORDER BY name
      `).bind(categoryFilter);
    } else {
      stmt = env.NEXUS_DB.prepare(`
        SELECT name, enabled, deployed, subdomain, port, public, core, admin_only, description, category, website, long_description, landing_path
        FROM services
        ORDER BY name
      `);
    }

    const results = await stmt.all();

    let pendingChangesCount = 0;
    const categoryCounts = {};
    const services = (results.results || []).map(row => {
      const enabled = row.enabled === 1;
      const deployed = row.deployed === 1;
      const hasPendingChange = enabled !== deployed;
      const category = row.category || '';

      if (hasPendingChange) {
        pendingChangesCount++;
      }

      // Build category statistics
      if (category) {
        if (!categoryCounts[category]) {
          categoryCounts[category] = { total: 0, enabled: 0, pending: 0 };
        }
        categoryCounts[category].total++;
        if (enabled) categoryCounts[category].enabled++;
        if (hasPendingChange) categoryCounts[category].pending++;
      }

      return {
        name: row.name,
        subdomain: row.subdomain || '',
        port: row.port || 0,
        public: row.public === 1,
        core: row.core === 1,
        admin_only: row.admin_only === 1,
        description: row.description || '',
        category,
        website: row.website || '',
        long_description: row.long_description || '',
        landing_path: row.landing_path || '',
        enabled,
        deployed,
        pending: hasPendingChange,
      };
    });

    return new Response(JSON.stringify({
      success: true,
      services,
      pendingChangesCount,
      categoryCounts,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services GET error:', error);
    await logError(env.NEXUS_DB, '/api/services', 'GET', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to load services',
      services: [],
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

/**
 * POST /api/services
 * Enable/disable a service (saves to D1 only, no deployment)
 * Use the Spin Up button to deploy changes
 */
export async function onRequestPost(context) {
  const { env, request } = context;

  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    // Reject oversized payloads based on actual byte size, not UTF-16 code units
    const bodyBuffer = await request.arrayBuffer();
    if (bodyBuffer.byteLength > 1048576) {
      return new Response(JSON.stringify({ success: false, error: 'Request body too large' }), {
        status: 413, headers: { 'Content-Type': 'application/json' },
      });
    }

    const body = JSON.parse(new TextDecoder().decode(bodyBuffer));
    const serviceName = body.service;
    const enabled = body.enabled;

    if (!serviceName || typeof enabled !== 'boolean') {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid payload. Expected { service: string, enabled: boolean }',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Validate service name format to prevent injection attacks
    if (!validateServiceName(serviceName)) {
      return new Response(JSON.stringify({
        success: false,
        error: `Invalid service name format. Service names must be 1-63 characters long and contain only lowercase letters, numbers, hyphens, and underscores.`,
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Check if service exists and get its core/admin_only status
    const service = await env.NEXUS_DB.prepare(
      'SELECT name, core, admin_only, deployed FROM services WHERE name = ?'
    ).bind(serviceName).first();

    if (!service) {
      return new Response(JSON.stringify({
        success: false,
        error: `Service not found: ${serviceName}. Run services init first.`,
      }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Block disabling core services
    if (service.core === 1 && !enabled) {
      return new Response(JSON.stringify({
        success: false,
        error: `Cannot disable ${serviceName} - it is a core service required for Nexus Stack operation`,
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Block toggling admin-only services
    if (service.admin_only === 1) {
      return new Response(JSON.stringify({
        success: false,
        error: `Cannot toggle ${serviceName} - it is an admin-only service managed via GitHub Actions`,
      }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Atomic batch: update + count pending + log
    const [, pendingResult] = await env.NEXUS_DB.batch([
      env.NEXUS_DB.prepare(
        `UPDATE services SET enabled = ?, updated_at = datetime('now') WHERE name = ?`
      ).bind(enabled ? 1 : 0, serviceName),
      env.NEXUS_DB.prepare(
        `SELECT COUNT(*) as count FROM services WHERE enabled != deployed`
      ),
    ]);
    const pendingChangesCount = pendingResult.results?.[0]?.count || 0;

    // Log outside the batch (non-critical)
    await logApiCall(env.NEXUS_DB, '/api/services', 'POST', {
      action: 'toggle_service',
      service: serviceName,
      enabled: enabled,
    });

    return new Response(JSON.stringify({
      success: true,
      message: `Service ${serviceName} ${enabled ? 'enabled' : 'disabled'}. Click "Spin Up" to deploy changes.`,
      pendingChangesCount,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services POST error:', error);
    await logError(env.NEXUS_DB, '/api/services', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to update service',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
