/**
 * Scheduled Teardown Worker
 * 
 * Runs daily to check if scheduled teardown is enabled and triggers:
 * 1. Email notification (15 minutes before teardown)
 * 2. Teardown workflow (at configured time)
 * 
 * Configuration stored in Cloudflare D1 database (NEXUS_DB)
 * - teardown_enabled: "true" | "false"
 * - teardown_timezone: "Europe/Zurich" (default)
 * - teardown_time: "22:00" (default)
 * - notification_time: "21:45" (default, 15 min before)
 */

// D1 Helper Functions
async function getConfigValue(db, key, defaultValue = null) {
  try {
    const result = await db.prepare('SELECT value FROM config WHERE key = ?').bind(key).first();
    return result ? result.value : defaultValue;
  } catch {
    return defaultValue;
  }
}

async function deleteConfigValue(db, key) {
  await db.prepare('DELETE FROM config WHERE key = ?').bind(key).run();
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduledTeardown(event, env));
  },

  async fetch(request, env) {
    // Health check endpoint
    if (request.url.endsWith('/health')) {
      return new Response(JSON.stringify({ status: 'ok', service: 'scheduled-teardown' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleScheduledTeardown(event, env) {
  try {
    // Check if D1 database is configured
    if (!env.NEXUS_DB) {
      console.log('D1 database not configured');
      return;
    }

    // Get configuration from D1
    const config = await getConfig(env.NEXUS_DB);
    
    if (config.enabled !== 'true') {
      console.log('Scheduled teardown is disabled');
      return;
    }

    // Check if teardown is delayed
    if (config.delayUntil) {
      const delayUntil = new Date(config.delayUntil);
      const now = new Date();
      if (now < delayUntil) {
        const hoursRemaining = Math.ceil((delayUntil - now) / (1000 * 60 * 60));
        console.log(`Scheduled teardown is delayed until ${delayUntil.toISOString()} (${hoursRemaining} hours remaining)`);
        return;
      } else {
        // Delay has expired, clear it
        await deleteConfigValue(env.NEXUS_DB, 'delay_until');
        console.log('Delay period expired, teardown will proceed');
      }
    }

    const now = new Date();
    const currentTime = now.toISOString();
    const cronTime = event.cron; // e.g., "0 21 * * *"
    
    console.log(`Scheduled event triggered at ${currentTime} (cron: ${cronTime})`);

    // Convert configured times from timezone to UTC
    const notificationTimeUTC = timeInTimezoneToUTC(config.notificationTime, config.timezone);
    const teardownTimeUTC = timeInTimezoneToUTC(config.teardownTime, config.timezone);
    
    // Get current UTC time components
    const currentHour = now.getUTCHours();
    const currentMinute = now.getUTCMinutes();
    const notificationHour = notificationTimeUTC.getUTCHours();
    const notificationMinute = notificationTimeUTC.getUTCMinutes();
    const teardownHour = teardownTimeUTC.getUTCHours();
    const teardownMinute = teardownTimeUTC.getUTCMinutes();
    
    // Check if it's notification time or teardown time
    if (currentHour === notificationHour && currentMinute === notificationMinute) {
      await sendNotification(env, config);
    } else if (currentHour === teardownHour && currentMinute === teardownMinute) {
      await triggerTeardown(env, config);
    } else {
      console.log(`Not time for notification (${notificationHour}:${String(notificationMinute).padStart(2, '0')} UTC) or teardown (${teardownHour}:${String(teardownMinute).padStart(2, '0')} UTC)`);
    }
  } catch (error) {
    console.error('Error in scheduled teardown:', error);
  }
}

async function getConfig(db) {
  const enabled = await getConfigValue(db, 'teardown_enabled', 'true');
  const timezone = await getConfigValue(db, 'teardown_timezone', 'Europe/Zurich');
  const teardownTime = await getConfigValue(db, 'teardown_time', '22:00');
  const notificationTime = await getConfigValue(db, 'notification_time', '21:45');
  const delayUntil = await getConfigValue(db, 'delay_until', null);
  
  return { enabled, timezone, teardownTime, notificationTime, delayUntil };
}

async function sendNotification(env, config) {
  if (!env.RESEND_API_KEY || !env.ADMIN_EMAIL || !env.DOMAIN) {
    console.log('Missing required environment variables for notification');
    return;
  }

  // Email recipients: User as primary, Admin in CC
  const userEmail = env.USER_EMAIL && env.USER_EMAIL.trim() !== '' ? env.USER_EMAIL : null;

  try {
    const teardownTime = `${config.teardownTime} ${getTimezoneAbbr(config.timezone)}`;
    
    const emailHtml = `
      <div style="font-family:monospace;background:#0a0a0f;color:#00ff88;padding:20px">
        <h1 style="color:#ffaa00">⚠️ Scheduled Teardown Reminder</h1>
        <p style="color:#fff">Your Nexus-Stack infrastructure will be automatically torn down in <strong style="color:#ffaa00">15 minutes</strong> (at ${teardownTime}).</p>
        <div style="margin:1.5rem 0;padding:1rem;background:#1a1a2e;border-left:3px solid #ffaa00">
          <p style="color:#ffaa00;margin:0;font-weight:bold">⏰ What happens next?</p>
          <ul style="color:#ccc;margin:0.5rem 0 0 1.5rem">
            <li>Infrastructure will be torn down automatically</li>
            <li>Hetzner server and Docker containers will be stopped</li>
            <li>Control Plane will remain active for re-deployment</li>
            <li>All data and state will be preserved</li>
          </ul>
        </div>
        <h2 style="color:#00ff88;margin-top:2rem">🛑 Want to prevent teardown?</h2>
        <p style="color:#fff">You can disable scheduled teardown via the Control Plane settings.</p>
        <h2 style="color:#00ff88;margin-top:2rem">🔗 Quick Links</h2>
        <ul>
          <li><a href="https://control.${env.DOMAIN}" style="color:#00ff88">Control Plane</a> - Manage infrastructure</li>
          <li><a href="https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions" style="color:#00ff88">GitHub Actions</a> - View workflows</li>
        </ul>
        <div style="margin-top:2rem;padding:1rem;background:#1a1a2e;border-left:3px solid #ffaa00">
          <p style="color:#ffaa00;margin:0;font-weight:bold">📮 Do not reply</p>
          <p style="color:#999;margin:0.5rem 0 0 0;font-size:13px">This mailbox is not monitored. For questions or support, please contact: <a href="mailto:${env.ADMIN_EMAIL}" style="color:#00ff88">${env.ADMIN_EMAIL}</a></p>
        </div>
        <p style="color:#666;font-size:12px;margin-top:1rem">This is an automated reminder. Infrastructure will be torn down automatically unless disabled.</p>
      </div>
    `;

    const emailPayload = {
      from: `Nexus-Stack <nexus@${env.DOMAIN}>`,
      to: userEmail ? [userEmail] : [env.ADMIN_EMAIL],
      subject: '⚠️ Scheduled Teardown in 15 Minutes',
      html: emailHtml,
    };
    if (userEmail) {
      emailPayload.cc = [env.ADMIN_EMAIL];
    }

    const response = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(emailPayload),
    });

    if (response.ok) {
      const recipientMsg = userEmail ? `${userEmail} (cc: ${env.ADMIN_EMAIL})` : env.ADMIN_EMAIL;
      console.log(`✅ Notification email sent to ${recipientMsg}`);
    } else {
      const error = await response.text();
      console.error(`⚠️ Failed to send notification: ${response.status} - ${error}`);
    }
  } catch (error) {
    console.error('Error sending notification:', error);
  }
}

async function triggerTeardown(env, config) {
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    console.log('Missing required environment variables for teardown');
    return;
  }

  try {
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/teardown.yml/dispatches`;
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Scheduled-Teardown',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: {
          confirm: 'TEARDOWN',
        },
      }),
    });

    if (response.status === 204) {
      console.log('✅ Teardown workflow triggered successfully');
    } else {
      const error = await response.text();
      console.error(`⚠️ Failed to trigger teardown: ${response.status} - ${error}`);
    }
  } catch (error) {
    console.error('Error triggering teardown:', error);
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

function getTimezoneAbbr(timezone) {
  // Simple timezone abbreviation mapping
  const tzMap = {
    'Europe/Zurich': 'CET',
    'America/New_York': 'EST',
    'America/Los_Angeles': 'PST',
  };
  return tzMap[timezone] || 'UTC';
}
