/**
 * Scheduled Teardown Configuration API
 * GET /api/scheduled-teardown - Get current configuration
 * POST /api/scheduled-teardown - Update configuration
 * 
 * Configuration stored in Cloudflare D1 database
 */

import { logApiCall, logError } from './_utils/logger.js';
import { getAccessUserEmail } from './_utils/cf-access-email.js';
import { requireAdmin } from './_utils/require-admin.js';
import { requireSameOrigin } from './_utils/require-same-origin.js';

// D1 Helper Functions
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

async function deleteConfig(db, key) {
  await db.prepare('DELETE FROM config WHERE key = ?').bind(key).run();
}

// Returns YYYY-MM-DD in UTC for use as a daily counter key
function utcDateKey() {
  return new Date().toISOString().slice(0, 10);
}

// Parse an env var as a positive integer with a fallback default.
// Guards against missing/empty/non-numeric values that would otherwise
// produce NaN and silently disable the limit checks.
function parsePositiveInt(value, fallback) {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

// Returns the number of extensions used today (UTC) for the given user
async function getExtensionsUsedToday(db, userEmail) {
  const key = `extensions_${utcDateKey()}_${userEmail || 'unknown'}`;
  const value = await getConfig(db, key, '0');
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

// Atomically increment the daily extension counter for the given user.
// Uses a single SQL statement with ON CONFLICT + RETURNING so two
// concurrent requests cannot both pass the limit check and increment.
async function incrementExtensionsUsedToday(db, userEmail) {
  const key = `extensions_${utcDateKey()}_${userEmail || 'unknown'}`;
  const result = await db.prepare(`
    INSERT INTO config (key, value, updated_at)
    VALUES (?, '1', datetime('now'))
    ON CONFLICT(key) DO UPDATE SET
      value = CAST(config.value AS INTEGER) + 1,
      updated_at = datetime('now')
    RETURNING CAST(value AS INTEGER) AS value
  `).bind(key).first();
  return result ? result.value : 1;
}

// Delete extension counter rows older than the given number of days (UTC).
// Best-effort: failures are swallowed so cleanup never breaks the request flow.
async function cleanupOldExtensionCounters(db, retainDays = 30) {
  try {
    const cutoff = new Date();
    cutoff.setUTCDate(cutoff.getUTCDate() - retainDays);
    const cutoffKey = `extensions_${cutoff.toISOString().slice(0, 10)}_`;
    await db.prepare(
      "DELETE FROM config WHERE key LIKE 'extensions_%' AND key < ?"
    ).bind(cutoffKey).run();
  } catch {
    // Cleanup is best-effort
  }
}

// Append a teardown extension audit log entry
async function logExtension(db, userEmail, delayHours, delayUntil) {
  try {
    const metadata = JSON.stringify({
      user: userEmail || 'unknown',
      delay_hours: delayHours,
      delay_until: delayUntil,
    });
    await db.prepare(
      "INSERT INTO logs (source, level, message, metadata) VALUES ('api', 'info', ?, ?)"
    ).bind(`Teardown extended by ${delayHours}h by ${userEmail || 'unknown'}`, metadata).run();
  } catch {
    // Audit logging is best-effort - don't fail the request if it errors
  }
}

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
  const { env, request } = context;
  const userEmail = getAccessUserEmail(request) || '';
  const maxExtensionsPerDay = parsePositiveInt(env.MAX_EXTENSIONS_PER_DAY, 3);
  const maxDelayHours = parsePositiveInt(env.MAX_DELAY_HOURS, 4);
  
  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const enabled = await getConfig(env.NEXUS_DB, 'teardown_enabled', 'true');
    const timezone = await getConfig(env.NEXUS_DB, 'teardown_timezone', 'Europe/Zurich');
    const teardownTime = await getConfig(env.NEXUS_DB, 'teardown_time', '22:00');
    const notificationTime = await getConfig(env.NEXUS_DB, 'notification_time', '21:45');
    const delayUntil = await getConfig(env.NEXUS_DB, 'delay_until', null);
    
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
    
    const extensionsUsed = await getExtensionsUsedToday(env.NEXUS_DB, userEmail);

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
        allowDisable: env.ALLOW_DISABLE_AUTO_SHUTDOWN === 'true',
        extensionsUsed,
        extensionsRemaining: Math.max(0, maxExtensionsPerDay - extensionsUsed),
        maxExtensionsPerDay,
        maxDelayHours,
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
  // Origin before identity: a cross-site submission carries a perfectly
  // valid Access session, so authenticating it first proves nothing.
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const denial = requireAdmin(env, request);
  if (denial) return denial;
  const userEmail = getAccessUserEmail(request) || '';
  const maxExtensionsPerDay = parsePositiveInt(env.MAX_EXTENSIONS_PER_DAY, 3);
  const maxDelayHours = parsePositiveInt(env.MAX_DELAY_HOURS, 4);

  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured'
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

    // Validate if disabling is allowed
    if (enabled === false && env.ALLOW_DISABLE_AUTO_SHUTDOWN !== 'true') {
      return new Response(JSON.stringify({
        success: false,
        error: 'Disabling auto-shutdown is not permitted by infrastructure policy',
      }), {
        status: 403,
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
      // Validate delayHours is a positive number within the configured max
      if (typeof delayHours !== 'number' || delayHours <= 0 || !Number.isFinite(delayHours)) {
        return new Response(JSON.stringify({
          success: false,
          error: 'delayHours must be a positive number',
        }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (delayHours > maxDelayHours) {
        return new Response(JSON.stringify({
          success: false,
          error: `delayHours must not exceed ${maxDelayHours} hours per request`,
        }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      // Atomically increment the counter first, then check the returned value.
      // This avoids a TOCTOU race where two concurrent requests both pass a
      // pre-increment check and then both increment, exceeding the daily limit.
      const newCount = await incrementExtensionsUsedToday(env.NEXUS_DB, userEmail);
      if (newCount > maxExtensionsPerDay) {
        // Roll back the over-limit increment so the counter stays at the cap
        const counterKey = `extensions_${utcDateKey()}_${userEmail || 'unknown'}`;
        await setConfig(env.NEXUS_DB, counterKey, String(maxExtensionsPerDay));
        return new Response(JSON.stringify({
          success: false,
          error: `Daily extension limit reached (${maxExtensionsPerDay} per day). Try again tomorrow.`,
          extensionsUsed: maxExtensionsPerDay,
          maxExtensionsPerDay,
        }), {
          status: 429,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      const delayMs = delayHours * 60 * 60 * 1000;
      const delayUntil = new Date(Date.now() + delayMs).toISOString();
      await setConfig(env.NEXUS_DB, 'delay_until', delayUntil);
      await logExtension(env.NEXUS_DB, userEmail, delayHours, delayUntil);
      // Best-effort cleanup of old extension counters (>30 days)
      await cleanupOldExtensionCounters(env.NEXUS_DB);
    }

    // Update D1 database
    if (enabled !== undefined) {
      await setConfig(env.NEXUS_DB, 'teardown_enabled', enabled ? 'true' : 'false');
      // Clear delay when disabling
      if (!enabled) {
        await deleteConfig(env.NEXUS_DB, 'delay_until');
      }
    }
    if (timezone) {
      await setConfig(env.NEXUS_DB, 'teardown_timezone', timezone);
    }
    if (teardownTime) {
      await setConfig(env.NEXUS_DB, 'teardown_time', teardownTime);
    }
    if (notificationTime) {
      await setConfig(env.NEXUS_DB, 'notification_time', notificationTime);
    }

    // Log config changes (exclude delay-only requests, those are logged by logExtension)
    if (enabled !== undefined || timezone || teardownTime || notificationTime) {
      await logApiCall(env.NEXUS_DB, '/api/scheduled-teardown', 'POST', {
        action: 'update_teardown_config',
        user: userEmail,
        ...(enabled !== undefined && { enabled }),
        ...(timezone && { timezone }),
        ...(teardownTime && { teardownTime }),
        ...(notificationTime && { notificationTime }),
      });
    }

    // Get updated config
    const updatedEnabled = await getConfig(env.NEXUS_DB, 'teardown_enabled', 'true');
    const updatedTimezone = await getConfig(env.NEXUS_DB, 'teardown_timezone', 'Europe/Zurich');
    const updatedTeardownTime = await getConfig(env.NEXUS_DB, 'teardown_time', '22:00');
    const updatedNotificationTime = await getConfig(env.NEXUS_DB, 'notification_time', '21:45');
    const updatedDelayUntil = await getConfig(env.NEXUS_DB, 'delay_until', null);

    const updatedExtensionsUsed = await getExtensionsUsedToday(env.NEXUS_DB, userEmail);

    return new Response(JSON.stringify({
      success: true,
      config: {
        enabled: updatedEnabled === 'true',
        timezone: updatedTimezone,
        teardownTime: updatedTeardownTime,
        notificationTime: updatedNotificationTime,
        delayUntil: updatedDelayUntil,
        allowDisable: env.ALLOW_DISABLE_AUTO_SHUTDOWN === 'true',
        extensionsUsed: updatedExtensionsUsed,
        extensionsRemaining: Math.max(0, maxExtensionsPerDay - updatedExtensionsUsed),
        maxExtensionsPerDay,
        maxDelayHours,
      },
      message: 'Configuration updated successfully',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    await logError(env.NEXUS_DB, '/api/scheduled-teardown', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
