/**
 * Scheduled Teardown Configuration API
 * GET /api/scheduled-teardown - Get current configuration
 * POST /api/scheduled-teardown - Update configuration
 * 
 * Configuration stored in Cloudflare KV (via Worker)
 */

export async function onRequestGet(context) {
  const { env } = context;
  
  if (!env.SCHEDULED_TEARDOWN) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Scheduled teardown worker not configured'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const enabled = await env.SCHEDULED_TEARDOWN.get('enabled') || 'false';
    const timezone = await env.SCHEDULED_TEARDOWN.get('timezone') || 'Europe/Zurich';
    const teardownTime = await env.SCHEDULED_TEARDOWN.get('teardown_time') || '22:00';
    const notificationTime = await env.SCHEDULED_TEARDOWN.get('notification_time') || '21:45';
    
    return new Response(JSON.stringify({
      success: true,
      config: {
        enabled: enabled === 'true',
        timezone,
        teardownTime,
        notificationTime,
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

export async function onRequestPost(context) {
  const { env, request } = context;
  
  if (!env.SCHEDULED_TEARDOWN) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Scheduled teardown worker not configured'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const body = await request.json();
    const { enabled, timezone, teardownTime, notificationTime } = body;

    // Validate input
    if (enabled !== undefined && enabled !== true && enabled !== false) {
      return new Response(JSON.stringify({
        success: false,
        error: 'enabled must be true or false',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Update KV store
    if (enabled !== undefined) {
      await env.SCHEDULED_TEARDOWN.put('enabled', enabled ? 'true' : 'false');
    }
    if (timezone) {
      await env.SCHEDULED_TEARDOWN.put('timezone', timezone);
    }
    if (teardownTime) {
      await env.SCHEDULED_TEARDOWN.put('teardown_time', teardownTime);
    }
    if (notificationTime) {
      await env.SCHEDULED_TEARDOWN.put('notification_time', notificationTime);
    }

    // Get updated config
    const updatedEnabled = await env.SCHEDULED_TEARDOWN.get('enabled') || 'false';
    const updatedTimezone = await env.SCHEDULED_TEARDOWN.get('timezone') || 'Europe/Zurich';
    const updatedTeardownTime = await env.SCHEDULED_TEARDOWN.get('teardown_time') || '22:00';
    const updatedNotificationTime = await env.SCHEDULED_TEARDOWN.get('notification_time') || '21:45';

    return new Response(JSON.stringify({
      success: true,
      config: {
        enabled: updatedEnabled === 'true',
        timezone: updatedTimezone,
        teardownTime: updatedTeardownTime,
        notificationTime: updatedNotificationTime,
      },
      message: 'Configuration updated successfully',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
