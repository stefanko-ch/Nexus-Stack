/**
 * Email Notification Settings API
 * GET /api/email-settings - Get current notification preferences
 * POST /api/email-settings - Update notification preferences
 *
 * Configuration stored in Cloudflare D1 database
 */
import { logApiCall, logError } from './_utils/logger.js';
import { requireAdmin } from './_utils/require-admin.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';

async function getConfig(db, key, defaultValue = null) {
  try {
    const result = await db.prepare('SELECT value FROM config WHERE key = ?').bind(key).first();
    return result ? result.value : defaultValue;
  } catch {
    return defaultValue;
  }
}

async function setConfig(db, key, value) {
  await db.prepare('INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, datetime("now"))').bind(key, value).run();
}

export async function onRequestGet(context) {
  const db = context.env.NEXUS_DB;
  if (!db) {
    return new Response(JSON.stringify({ success: false, error: 'D1 database not configured' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    const notifyOnShutdown = await getConfig(db, 'notify_on_shutdown', 'true');
    const notifyOnSpinup = await getConfig(db, 'notify_on_spinup', 'true');
    const silentMode = await getConfig(db, 'silent_mode', 'false');

    return new Response(JSON.stringify({
      success: true,
      settings: {
        notifyOnShutdown: notifyOnShutdown === 'true',
        notifyOnSpinup: notifyOnSpinup === 'true',
        silentMode: silentMode === 'true',
      }
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

export async function onRequestPost(context) {
  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(context.request);
  if (crossSite) return crossSite;
  const denial = requireAdmin(context.env, context.request);
  if (denial) return denial;

  const db = context.env.NEXUS_DB;
  if (!db) {
    return new Response(JSON.stringify({ success: false, error: 'D1 database not configured' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    const body = await context.request.json();

    if (body.notifyOnShutdown !== undefined) {
      if (typeof body.notifyOnShutdown !== 'boolean') {
        return new Response(JSON.stringify({ success: false, error: 'notifyOnShutdown must be a boolean' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      await setConfig(db, 'notify_on_shutdown', body.notifyOnShutdown ? 'true' : 'false');
      // Enabling a toggle implicitly disables silent mode
      if (body.notifyOnShutdown) {
        await setConfig(db, 'silent_mode', 'false');
      }
    }

    if (body.notifyOnSpinup !== undefined) {
      if (typeof body.notifyOnSpinup !== 'boolean') {
        return new Response(JSON.stringify({ success: false, error: 'notifyOnSpinup must be a boolean' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      await setConfig(db, 'notify_on_spinup', body.notifyOnSpinup ? 'true' : 'false');
      // Enabling a toggle implicitly disables silent mode
      if (body.notifyOnSpinup) {
        await setConfig(db, 'silent_mode', 'false');
      }
    }

    // Return updated state
    const notifyOnShutdown = await getConfig(db, 'notify_on_shutdown', 'true');
    const notifyOnSpinup = await getConfig(db, 'notify_on_spinup', 'true');
    const silentMode = await getConfig(db, 'silent_mode', 'false');

    await logApiCall(db, '/api/email-settings', 'POST', {
      action: 'update_email_settings',
      notifyOnShutdown: notifyOnShutdown === 'true',
      notifyOnSpinup: notifyOnSpinup === 'true',
      silentMode: silentMode === 'true',
    });

    return new Response(JSON.stringify({
      success: true,
      settings: {
        notifyOnShutdown: notifyOnShutdown === 'true',
        notifyOnSpinup: notifyOnSpinup === 'true',
        silentMode: silentMode === 'true',
      }
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    await logError(db, '/api/email-settings', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
