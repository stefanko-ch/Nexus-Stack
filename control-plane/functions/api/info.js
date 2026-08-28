/**
 * Get infrastructure information
 * GET /api/info
 *
 * Returns server info, time information, scheduled teardown details, and workflow details
 * Configuration stored in Cloudflare D1 database
 */
import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { ALL_SPINUP_WORKFLOWS, ALL_TEARDOWN_WORKFLOWS } from './_utils/workflow-selection.js';

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

  // The local calendar date in the target zone, e.g. "2026-08-27".
  const dateStr = baseDate.toLocaleDateString('en-CA', { timeZone: timezone });

  // The wanted wall-clock moment, read as if it were UTC. Not the answer —
  // it is off by exactly the zone's offset, which the passes below measure.
  const naive = new Date(
    `${dateStr}T${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:00Z`
  ).getTime();

  // Measure the offset by formatting an instant in the zone and reading the
  // FULL local date back, not just hours and minutes.
  //
  // Reading only hh:mm is what made "next teardown" show tomorrow: for a
  // late local time the probe lands on the next day in the zone (22:00Z is
  // 00:00 in Europe/Zurich), so 22:00 versus 00:00 measured +1320 minutes
  // instead of -120. Folding that modulo a day fixes Zurich but stays
  // ambiguous near ±12h, where UTC+14 and UTC+10 give the same remainder.
  const offsetMsAt = (instant) => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).formatToParts(instant);

    const f = {};
    for (const p of parts) {
      if (p.type !== 'literal') f[p.type] = p.value;
    }

    // hour comes back as "24" rather than "00" at midnight in some runtimes.
    const localAsUTC = Date.UTC(
      Number(f.year),
      Number(f.month) - 1,
      Number(f.day),
      Number(f.hour) % 24,
      Number(f.minute),
      Number(f.second)
    );
    return localAsUTC - instant.getTime();
  };

  // Two passes, because the offset has to be the one in force at the ANSWER,
  // not at the probe. They differ across a daylight-saving transition: on
  // 2026-03-29 in Europe/Zurich, 01:30Z is already 03:30 local, so a single
  // pass measures +2h and returns 00:30 local for a requested 01:30.
  //
  // The second pass re-measures at the candidate instant and converges. A
  // clock time that does not exist — 02:30 on a spring-forward day — maps
  // forward to 03:30, which is what zoneinfo and the JDK also do.
  const firstPass = naive - offsetMsAt(new Date(naive));
  return new Date(naive - offsetMsAt(new Date(firstPass)));
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
    let hostOs = null;
    let hostDiskGb = null;
    let hostDocker = null;

    if (env.NEXUS_DB) {
      serverType = await getConfig(env.NEXUS_DB, 'server_type', null);
      serverLocation = await getConfig(env.NEXUS_DB, 'server_location', null);
      domain = await getConfig(env.NEXUS_DB, 'domain', null);
      lastSpinUp = await getConfig(env.NEXUS_DB, 'last_spin_up', null);
      lastTeardown = await getConfig(env.NEXUS_DB, 'last_teardown', null);
      // Host facts, collected over ssh during the last spin-up. Absent
      // when that lookup failed or on a stack deployed before this
      // existed — the UI renders those as "—" rather than guessing.
      hostOs = await getConfig(env.NEXUS_DB, 'host_os', null);
      hostDiskGb = await getConfig(env.NEXUS_DB, 'host_disk_gb', null);
      hostDocker = await getConfig(env.NEXUS_DB, 'host_docker', null);
    }

    // Fallback to env vars if D1 doesn't have values
    if (!serverType) serverType = env.SERVER_TYPE || null;
    if (!serverLocation) serverLocation = env.SERVER_LOCATION || null;
    if (!domain) domain = env.DOMAIN || null;

    // Validate domain as a hostname to prevent HTML/attribute injection
    // when the UI interpolates it into hrefs. Allows alphanumerics, dots,
    // and hyphens (standard DNS label characters); rejects scheme, slash,
    // whitespace, quotes, or any other structural characters.
    if (domain && !/^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$/i.test(domain)) {
      domain = null;
    }

    // Allowlist subdomain separator to prevent HTML/attribute injection
    // when the UI concatenates this value into stack link hrefs.
    const rawSeparator = env.SUBDOMAIN_SEPARATOR;
    const subdomainSeparator = (rawSeparator === '.' || rawSeparator === '-') ? rawSeparator : '.';

    info.server = {
      type: serverType,
      location: serverLocation,
      domain: domain,
      subdomainSeparator,
      lastSpinUp: lastSpinUp,
      lastTeardown: lastTeardown,
      // Read from the box itself rather than derived from the server
      // type: a snapshot restored onto a larger type ratchets the disk
      // permanently upward, so type and disk can legitimately disagree.
      os: hostOs,
      diskGb: hostDiskGb,
      docker: hostDocker,
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
    const workflowResponse = await fetchWithTimeout(workflowUrl, {
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
        ((r.path && ALL_SPINUP_WORKFLOWS.some((w) => r.path.includes(w))) ||
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
        ((r.path && ALL_TEARDOWN_WORKFLOWS.some((w) => r.path.includes(w))) ||
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
