/**
 * Sync deployed state after successful spin-up
 * POST /api/services/sync-deployed
 * 
 * Called by spin-up workflow after successful deployment.
 * Sets deployed = enabled for all services (deployment is now in sync).
 */

import { logApiCall, logError } from '../_utils/logger.js';

export async function onRequestPost(context) {
  const { env } = context;

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
    // Set deployed = enabled for all services
    const result = await env.NEXUS_DB.prepare(`
      UPDATE services SET deployed = enabled, updated_at = datetime('now')
    `).run();

    await logApiCall(env.NEXUS_DB, '/api/services/sync-deployed', 'POST', {
      action: 'sync_deployed',
      rowsAffected: result.meta?.changes || 0,
    });

    return new Response(JSON.stringify({
      success: true,
      message: 'Deployed state synced with enabled state',
      rowsAffected: result.meta?.changes || 0,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Sync deployed error:', error);
    await logError(env.NEXUS_DB, '/api/services/sync-deployed', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to sync deployed state',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
