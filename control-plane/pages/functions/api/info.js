/**
 * Get infrastructure information
 * GET /api/info
 * 
 * Returns server info, time information, scheduled teardown details, and workflow details
 * Configuration stored in Cloudflare D1 database
 */

// D1 Helper Functions
async function getConfig(db, key, defaultValue = null) {
  try {
    const result = await db.prepare('SELECT value FROM config WHERE key = ?').bind(key).first();
    return result ? result.value : defaultValue;
  } catch {
    return defaultValue;
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
  const { env } = context;
  
  // Validate environment variables
  const missing = [];
  if (!env.GITHUB_TOKEN) missing.push('GITHUB_TOKEN');
  if (!env.GITHUB_OWNER) missing.push('GITHUB_OWNER');
  if (!env.GITHUB_REPO) missing.push('GITHUB_REPO');
  
  if (missing.length > 0) {
    return new Response(JSON.stringify({ 
      success: false, 
      error: `Missing required environment variables: ${missing.join(', ')}` 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const info = {
      server: {},
      time: {},
      scheduledTeardown: {},
      workflows: {},
    };

    // Get server info from D1 config (primary) or env vars (fallback)
    let serverType = null;
    let serverLocation = null;
    let domain = null;
    let lastSpinUp = null;
    let lastTeardown = null;

    if (env.NEXUS_DB) {
      serverType = await getConfig(env.NEXUS_DB, 'server_type', null);
      serverLocation = await getConfig(env.NEXUS_DB, 'server_location', null);
      domain = await getConfig(env.NEXUS_DB, 'domain', null);
      lastSpinUp = await getConfig(env.NEXUS_DB, 'last_spin_up', null);
      lastTeardown = await getConfig(env.NEXUS_DB, 'last_teardown', null);
    }

    // Fallback to env vars if D1 doesn't have values
    if (!serverType) serverType = env.SERVER_TYPE || null;
    if (!serverLocation) serverLocation = env.SERVER_LOCATION || null;
    if (!domain) domain = env.DOMAIN || null;

    info.server = {
      type: serverType,
      location: serverLocation,
      domain: domain,
      lastSpinUp: lastSpinUp,
      lastTeardown: lastTeardown,
    };

    // Get scheduled teardown config from D1
    if (env.NEXUS_DB) {
      const enabled = await getConfig(env.NEXUS_DB, 'teardown_enabled', 'true');
      const timezone = await getConfig(env.NEXUS_DB, 'teardown_timezone', 'Europe/Zurich');
      const teardownTime = await getConfig(env.NEXUS_DB, 'teardown_time', '22:00');
      const delayUntil = await getConfig(env.NEXUS_DB, 'delay_until', null);
      
      info.scheduledTeardown = {
        enabled: enabled === 'true',
        timezone,
        teardownTime,
        delayUntil,
      };

      // Calculate next teardown time
      if (enabled === 'true') {
        // Validate teardownTime format
        const timeFormatRegex = /^([0-1][0-9]|2[0-3]):[0-5][0-9]$/;
        if (!timeFormatRegex.test(teardownTime)) {
          // Log warning for invalid format
          console.warn(`Invalid teardown_time format in D1: "${teardownTime}". Expected HH:MM format. Skipping next teardown calculation.`);
          // Skip calculation if invalid format
          info.scheduledTeardown.nextTeardown = null;
          info.scheduledTeardown.timeRemaining = null;
        } else {
          const now = new Date();
          
          // Convert configured time in timezone to UTC
          let nextTeardown = timeInTimezoneToUTC(teardownTime, timezone);
          
          // If the time has already passed today, move to tomorrow
          if (nextTeardown <= now) {
            const tomorrow = new Date(nextTeardown);
            tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
            nextTeardown = timeInTimezoneToUTC(teardownTime, timezone, tomorrow);
          }

          // Apply delay if exists
          if (delayUntil) {
            const delayDate = new Date(delayUntil);
            if (delayDate > nextTeardown) {
              info.scheduledTeardown.nextTeardown = delayDate.toISOString();
              info.scheduledTeardown.delayed = true;
            } else {
              info.scheduledTeardown.nextTeardown = nextTeardown.toISOString();
              info.scheduledTeardown.delayed = false;
            }
          } else {
            info.scheduledTeardown.nextTeardown = nextTeardown.toISOString();
            info.scheduledTeardown.delayed = false;
          }

          // Calculate time remaining
          const timeRemaining = new Date(info.scheduledTeardown.nextTeardown) - now;
          const hoursRemaining = Math.floor(timeRemaining / (1000 * 60 * 60));
          const minutesRemaining = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
          info.scheduledTeardown.timeRemaining = {
            hours: hoursRemaining,
            minutes: minutesRemaining,
            totalMinutes: Math.floor(timeRemaining / (1000 * 60)),
          };
        }
      }
    }

    // Get workflow details from GitHub API
    const workflowUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs?per_page=20`;
    const workflowResponse = await fetch(workflowUrl, {
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Plane',
      },
    });

    if (workflowResponse.ok) {
      const workflowData = await workflowResponse.json();
      const runs = workflowData.workflow_runs || [];

      // Find last successful spin-up (preferred) or setup
      const lastSpinUp = runs.find(r => 
        ((r.path && r.path.includes('spin-up.yml')) || 
         (r.name && (r.name.includes('Spin Up') || r.name.includes('Spin-Up')))) &&
        r.conclusion === 'success'
      );

      const lastSetup = runs.find(r => 
        ((r.path && r.path.includes('setup-control-plane.yaml')) || 
         (r.name && r.name.includes('Setup'))) &&
        r.conclusion === 'success'
      );

      // Find last successful teardown
      const lastTeardown = runs.find(r => 
        ((r.path && r.path.includes('teardown.yml')) || 
         (r.name && r.name.includes('Teardown'))) &&
        r.conclusion === 'success'
      );

      const deploySource = lastSpinUp || lastSetup;

      if (deploySource) {
        const deployTime = new Date(deploySource.updated_at);
        const now = new Date();
        const uptimeMs = now - deployTime;
        const uptimeHours = Math.floor(uptimeMs / (1000 * 60 * 60));
        const uptimeDays = Math.floor(uptimeHours / 24);
        const uptimeMinutes = Math.floor((uptimeMs % (1000 * 60 * 60)) / (1000 * 60));

        info.time = {
          lastDeploy: deploySource.updated_at,
          lastTeardown: lastTeardown ? lastTeardown.updated_at : null,
          uptime: {
            days: uptimeDays,
            hours: uptimeHours % 24,
            minutes: uptimeMinutes,
            totalHours: uptimeHours,
          },
        };

        info.workflows = {
          lastDeploy: deploySource ? {
            time: deploySource.updated_at,
            status: deploySource.status,
            conclusion: deploySource.conclusion,
            url: deploySource.html_url,
          } : null,
          lastSetup: lastSetup ? {
            time: lastSetup.updated_at,
            status: lastSetup.status,
            conclusion: lastSetup.conclusion,
            url: lastSetup.html_url,
          } : null,
          lastSpinUp: lastSpinUp ? {
            time: lastSpinUp.updated_at,
            status: lastSpinUp.status,
            conclusion: lastSpinUp.conclusion,
            url: lastSpinUp.html_url,
          } : null,
          lastTeardown: lastTeardown ? {
            time: lastTeardown.updated_at,
            status: lastTeardown.status,
            conclusion: lastTeardown.conclusion,
            url: lastTeardown.html_url,
          } : null,
        };
      }
    }

    return new Response(JSON.stringify({
      success: true,
      info,
    }), {
      headers: { 
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (error) {
    console.error('Info endpoint error:', error);
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Internal server error' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
