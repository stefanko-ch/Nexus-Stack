/**
 * Scheduled Teardown Configuration API
 * GET /api/scheduled-teardown - Get current configuration
 * POST /api/scheduled-teardown - Update configuration
 * 
 * Configuration stored in Cloudflare KV (via Worker)
 */

/**
 * Convert a time in a specific timezone to UTC Date
 * @param {string} timeStr - Time in HH:MM format
 * @param {string} timezone - IANA timezone (e.g., 'Europe/Zurich')
 * @param {Date} baseDate - Base date to use (defaults to today)
 * @returns {Date} - Date object representing the time in UTC
 */
function timeInTimezoneToUTC(timeStr, timezone, baseDate = new Date()) {
  const [hours, minutes] = timeStr.split(':').map(Number);
  
  // Get the date string in the target timezone
  const dateStr = baseDate.toLocaleDateString('en-CA', { timeZone: timezone }); // YYYY-MM-DD
  
  // Create a date assuming the time is in UTC
  const utcDate = new Date(`${dateStr}T${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:00Z`);
  
  // Now format this UTC date in the target timezone to see what time it represents there
  const tzFormatter = new Intl.DateTimeFormat('en', {
    timeZone: timezone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  
  const tzTimeStr = tzFormatter.format(utcDate);
  const [tzHours, tzMinutes] = tzTimeStr.split(':').map(Number);
  
  // Calculate the difference between desired time and actual time in timezone
  const desiredMinutes = hours * 60 + minutes;
  const actualMinutes = tzHours * 60 + tzMinutes;
  const diffMinutes = desiredMinutes - actualMinutes;
  
  // Adjust UTC date by the difference
  const adjustedDate = new Date(utcDate.getTime() + diffMinutes * 60 * 1000);
  
  return adjustedDate;
}

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
    const enabled = await env.SCHEDULED_TEARDOWN.get('enabled') || 'true';
    const timezone = await env.SCHEDULED_TEARDOWN.get('timezone') || 'Europe/Zurich';
    const teardownTime = await env.SCHEDULED_TEARDOWN.get('teardown_time') || '22:00';
    const notificationTime = await env.SCHEDULED_TEARDOWN.get('notification_time') || '21:45';
    const delayUntil = await env.SCHEDULED_TEARDOWN.get('delay_until') || null;
    
    // Calculate next teardown time
    let nextTeardown = null;
    let timeRemaining = null;
    if (enabled === 'true') {
      // Validate teardownTime format
      const timeFormatRegex = /^([0-1][0-9]|2[0-3]):[0-5][0-9]$/;
      if (!timeFormatRegex.test(teardownTime)) {
        throw new Error(`Invalid teardown_time format: ${teardownTime}. Expected HH:MM format.`);
      }

      const now = new Date();
      
      // Convert configured time in timezone to UTC
      let nextTeardownDate = timeInTimezoneToUTC(teardownTime, timezone);
      
      // If the time has already passed today, move to tomorrow
      if (nextTeardownDate <= now) {
        const tomorrow = new Date(nextTeardownDate);
        tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
        nextTeardownDate = timeInTimezoneToUTC(teardownTime, timezone, tomorrow);
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

    // Validate time format (HH:MM)
    const timeFormatRegex = /^([0-1][0-9]|2[0-3]):[0-5][0-9]$/;
    if (teardownTime && !timeFormatRegex.test(teardownTime)) {
      return new Response(JSON.stringify({
        success: false,
        error: 'teardownTime must be in HH:MM format (e.g., "22:00")',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (notificationTime && !timeFormatRegex.test(notificationTime)) {
      return new Response(JSON.stringify({
        success: false,
        error: 'notificationTime must be in HH:MM format (e.g., "21:45")',
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
    const updatedEnabled = await env.SCHEDULED_TEARDOWN.get('enabled') || 'true';
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
