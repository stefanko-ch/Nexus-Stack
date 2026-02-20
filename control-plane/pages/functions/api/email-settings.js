/**
 * Email Notification Settings API
 * GET /api/email-settings - Get current notification preferences
 * POST /api/email-settings - Update notification preferences
 *
 * Configuration stored in Cloudflare D1 database
 */

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
  try {
    const db = context.env.NEXUS_DB;

    const notifyOnShutdown = await getConfig(db, 'notify_on_shutdown', 'true');
    const notifyOnSpinup = await getConfig(db, 'notify_on_spinup', 'true');

    return new Response(JSON.stringify({
      success: true,
      settings: {
        notifyOnShutdown: notifyOnShutdown === 'true',
        notifyOnSpinup: notifyOnSpinup === 'true',
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
  try {
    const db = context.env.NEXUS_DB;
    const body = await context.request.json();

    if (body.notifyOnShutdown !== undefined) {
      await setConfig(db, 'notify_on_shutdown', body.notifyOnShutdown ? 'true' : 'false');
    }

    if (body.notifyOnSpinup !== undefined) {
      await setConfig(db, 'notify_on_spinup', body.notifyOnSpinup ? 'true' : 'false');
    }

    // Return updated state
    const notifyOnShutdown = await getConfig(db, 'notify_on_shutdown', 'true');
    const notifyOnSpinup = await getConfig(db, 'notify_on_spinup', 'true');

    return new Response(JSON.stringify({
      success: true,
      settings: {
        notifyOnShutdown: notifyOnShutdown === 'true',
        notifyOnSpinup: notifyOnSpinup === 'true',
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
