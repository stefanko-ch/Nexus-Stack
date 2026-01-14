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
    const delayUntil = await env.SCHEDULED_TEARDOWN.get('delay_until') || null;
    
    // Calculate next teardown time
    let nextTeardown = null;
    let timeRemaining = null;
    if (enabled === 'true') {
      const now = new Date();
      const [hours, minutes] = teardownTime.split(':').map(Number);
      
      // Create next teardown date (today or tomorrow) - adjust for timezone
      const nextTeardownDate = new Date();
      nextTeardownDate.setUTCHours(hours, minutes, 0, 0);
      if (nextTeardownDate <= now) {
        nextTeardownDate.setUTCDate(nextTeardownDate.getUTCDate() + 1);
      }

      // Apply delay if exists
      if (delayUntil) {
        const delayDate = new Date(delayUntil);
        if (delayDate > nextTeardownDate) {
          nextTeardown = delayDate.toISOString();
        } else {
          nextTeardown = nextTeardownDate.toISOString();
        }
      } else {
        nextTeardown = nextTeardownDate.toISOString();
      }

      // Calculate time remaining
      const remaining = new Date(nextTeardown) - now;
      const hoursRemaining = Math.floor(remaining / (1000 * 60 * 60));
      const minutesRemaining = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
      timeRemaining = {
        hours: hoursRemaining,
        minutes: minutesRemaining,
        totalMinutes: Math.floor(remaining / (1000 * 60)),
      };
    }
    
    return new Response(JSON.stringify({
      success: true,
      config: {
        enabled: enabled === 'true',
        timezone,
        teardownTime,
        notificationTime,
        delayUntil,
        nextTeardown,
        timeRemaining,
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
    const { enabled, timezone, teardownTime, notificationTime, delayHours } = body;

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

    // Handle delay request
    if (delayHours !== undefined) {
      const delayMs = delayHours * 60 * 60 * 1000;
      const delayUntil = new Date(Date.now() + delayMs).toISOString();
      await env.SCHEDULED_TEARDOWN.put('delay_until', delayUntil);
    }

    // Update KV store
    if (enabled !== undefined) {
      await env.SCHEDULED_TEARDOWN.put('enabled', enabled ? 'true' : 'false');
      // Clear delay when disabling
      if (!enabled) {
        await env.SCHEDULED_TEARDOWN.delete('delay_until');
      }
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
    const updatedDelayUntil = await env.SCHEDULED_TEARDOWN.get('delay_until') || null;

    return new Response(JSON.stringify({
      success: true,
      config: {
        enabled: updatedEnabled === 'true',
        timezone: updatedTimezone,
        teardownTime: updatedTeardownTime,
        notificationTime: updatedNotificationTime,
        delayUntil: updatedDelayUntil,
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
