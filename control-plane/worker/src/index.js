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

// Duplicates functions/api/_utils/url.js. The worker is deployed as a single
// raw file via Terraform (tofu/control-plane/main.tf -> file(...)), so it cannot
// import from the Pages Functions _utils/ tree without introducing a bundler.

// Resend-accepted email formats. Hoisted to module scope so the regex
// objects are created once per Worker boot instead of once per notification.
//   plain:     `email@example.com` (no angle brackets)
//   bracketed: `Name <email@example.com>` (non-empty display name + both brackets)
const PLAIN_EMAIL_RE = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/;
const BRACKETED_EMAIL_RE = /^\S[^<>]*<[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+>$/;
const isValidResendEmail = (e) => PLAIN_EMAIL_RE.test(e) || BRACKETED_EMAIL_RE.test(e);

function validateHttpsOrigin(url) {
  if (!url) return null;
  try {
    const u = new URL(url);
    if (u.protocol !== 'https:') return null;
    return u.origin;
  } catch {
    return null;
  }
}

function safeHttpsUrl(candidate, fallback) {
  return validateHttpsOrigin(candidate) || validateHttpsOrigin(fallback) || '';
}

// Fetch with timeout to prevent hanging requests
async function fetchWithTimeout(url, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

// D1 Helper Functions
async function getConfigValue(db, key, defaultValue = null) {
  try {
    const result = await db.prepare('SELECT value FROM config WHERE key = ?').bind(key).first();
    return result ? result.value : defaultValue;
  } catch (error) {
    console.error('Failed to get config value from D1 for key:', key, error);
    return defaultValue;
  }
}

async function deleteConfigValue(db, key) {
  await db.prepare('DELETE FROM config WHERE key = ?').bind(key).run();
}

async function logToD1(db, level, message, metadata = null) {
  if (!db) return;
  try {
    const metadataJson = metadata ? JSON.stringify(metadata) : null;
    await db.prepare(
      'INSERT INTO logs (source, level, message, metadata) VALUES (?, ?, ?, ?)'
    ).bind('worker', level, message, metadataJson).run();
  } catch (error) {
    console.error('Failed to log to D1:', error);
  }
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduledTeardown(event, env));
    // Run log cleanup weekly (on the first cron trigger)
    ctx.waitUntil(cleanupOldLogs(env));
  },

  async fetch(request, env) {
    // Basic health check endpoint - just confirms the worker is reachable
    if (request.url.endsWith('/health')) {
      return new Response(JSON.stringify({ status: 'ok', service: 'scheduled-teardown' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Diagnostic health check - verifies all bindings and secrets are configured.
    // Used by the setup workflow to fail loudly if anything is missing after deploy.
    // Does NOT expose secret values - only reports presence (true/false).
    //
    // GATED: requires Authorization: Bearer <GITHUB_TOKEN> header. Both the
    // worker and the setup workflow already have this secret, so we reuse it
    // instead of introducing a new one. The workers.dev URL is publicly
    // reachable, so without this gate the diagnostic would leak which
    // bindings/secrets are configured (useful reconnaissance).
    if (request.url.endsWith('/health/diagnostic')) {
      const authHeader = request.headers.get('Authorization') || '';
      const expectedToken = env.GITHUB_TOKEN || '';
      const providedToken = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';

      if (!expectedToken || !constantTimeEqual(providedToken, expectedToken)) {
        return new Response(JSON.stringify({
          status: 'error',
          error: 'Forbidden: missing or invalid Authorization header',
        }), {
          status: 403,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      const checks = {
        bindings: {
          NEXUS_DB: !!env.NEXUS_DB,
        },
        env_vars: {
          DOMAIN: !!env.DOMAIN,
          ADMIN_EMAIL: !!env.ADMIN_EMAIL,
          GITHUB_OWNER: !!env.GITHUB_OWNER,
          GITHUB_REPO: !!env.GITHUB_REPO,
          NOTIFICATION_CRON: !!env.NOTIFICATION_CRON,
          TEARDOWN_CRON: !!env.TEARDOWN_CRON,
        },
        secrets: {
          GITHUB_TOKEN: !!env.GITHUB_TOKEN,
          RESEND_API_KEY: !!env.RESEND_API_KEY,
        },
        d1_query: false,
      };

      // Verify the D1 binding actually works by running a trivial query
      if (env.NEXUS_DB) {
        try {
          await env.NEXUS_DB.prepare('SELECT 1 AS ok').first();
          checks.d1_query = true;
        } catch (error) {
          checks.d1_query = false;
          checks.d1_error = error.message;
        }
      }

      // Determine overall status. Required items are everything the worker
      // needs to function correctly. RESEND_API_KEY is intentionally NOT
      // required because the existing setup workflow treats it as optional
      // (notifications are disabled when missing).
      const required = [
        checks.bindings.NEXUS_DB,
        checks.env_vars.DOMAIN,
        checks.env_vars.ADMIN_EMAIL,
        checks.env_vars.GITHUB_OWNER,
        checks.env_vars.GITHUB_REPO,
        checks.env_vars.NOTIFICATION_CRON,
        checks.env_vars.TEARDOWN_CRON,
        checks.secrets.GITHUB_TOKEN,
        checks.d1_query,
      ];
      const allRequiredOk = required.every(Boolean);
      const status = allRequiredOk ? 'ok' : 'error';
      const httpStatus = allRequiredOk ? 200 : 503;

      return new Response(JSON.stringify({
        status,
        service: 'scheduled-teardown',
        checks,
      }, null, 2), {
        status: httpStatus,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};

// Constant-time string comparison to mitigate timing attacks against the
// diagnostic endpoint's bearer token check.
function constantTimeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) {
    return false;
  }
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

// Clean up logs older than 30 days
async function cleanupOldLogs(env) {
  if (!env.NEXUS_DB) return;

  try {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 30);
    const cutoffStr = cutoff.toISOString().replace('T', ' ').substring(0, 19);

    const result = await env.NEXUS_DB.prepare(
      'DELETE FROM logs WHERE created_at < ?'
    ).bind(cutoffStr).run();

    const deletedCount = result.meta?.changes || 0;
    if (deletedCount > 0) {
      console.log(`Cleaned up ${deletedCount} old log entries`);
      await logToD1(env.NEXUS_DB, 'info', 'Log cleanup completed', { deletedCount });
    }
  } catch (error) {
    console.error('Failed to cleanup old logs:', error);
  }
}

async function handleScheduledTeardown(event, env) {
  try {
    // Fail fast if critical bindings are missing
    if (!env.NEXUS_DB) {
      console.error('D1 database not configured');
      return;
    }
    const requiredVars = ['GITHUB_TOKEN', 'GITHUB_OWNER', 'GITHUB_REPO', 'DOMAIN'];
    const missing = requiredVars.filter(v => !env[v]);
    if (missing.length > 0) {
      const msg = `Missing required environment variables: ${missing.join(', ')}`;
      console.error(msg);
      await logToD1(env.NEXUS_DB, 'error', msg, { missing });
      return;
    }

    // Log worker execution
    await logToD1(env.NEXUS_DB, 'info', 'Scheduled worker triggered', {
      cron: event.cron,
      timestamp: new Date().toISOString(),
    });

    // Get configuration from D1
    const config = await getConfig(env.NEXUS_DB);

    if (config.enabled !== 'true') {
      await logToD1(env.NEXUS_DB, 'debug', 'Scheduled teardown is disabled');
      console.log('Scheduled teardown is disabled');
      return;
    }

    // Check if teardown is delayed
    if (config.delayUntil) {
      const delayUntil = new Date(config.delayUntil);
      const now = new Date();
      if (now < delayUntil) {
        const hoursRemaining = Math.ceil((delayUntil - now) / (1000 * 60 * 60));
        await logToD1(env.NEXUS_DB, 'info', 'Teardown delayed', {
          delayUntil: delayUntil.toISOString(),
          hoursRemaining,
        });
        console.log(`Scheduled teardown is delayed until ${delayUntil.toISOString()} (${hoursRemaining} hours remaining)`);
        return;
      } else {
        // Delay has expired, clear it
        await deleteConfigValue(env.NEXUS_DB, 'delay_until');
        await logToD1(env.NEXUS_DB, 'info', 'Delay expired, teardown will proceed');
        console.log('Delay period expired, teardown will proceed');
      }
    }

    // Check if infrastructure is actually deployed before proceeding
    // Fail-closed: skip teardown for any non-deployed or unknown state
    const infraState = await checkInfraStatus(env);
    if (infraState === 'torn-down' || infraState === 'offline') {
      const message = `Infrastructure is not deployed (state: ${infraState}), skipping scheduled teardown`;
      console.log(message);
      await logToD1(env.NEXUS_DB, 'info', message, { infraState });
      return;
    }
    if (infraState === 'unknown') {
      const message = 'Could not determine infrastructure state (GitHub API unreachable?), skipping teardown as safety precaution';
      console.warn(message);
      await logToD1(env.NEXUS_DB, 'warn', message, { infraState });
      return;
    }

    const now = new Date();
    const currentTime = now.toISOString();
    const cronSchedule = event.cron; // e.g., "0 21 * * *" or "45 20 * * *"

    console.log(`Scheduled event triggered at ${currentTime} (cron: ${cronSchedule})`);

    // Determine action based on which cron trigger fired
    // Cron schedules are configurable via environment variables (set in tofu/control-plane/main.tf)
    // Defaults: NOTIFICATION_CRON="45 20 * * *" (20:45 UTC), TEARDOWN_CRON="0 21 * * *"
    // If environment variables are missing or empty, defaults are used. If incorrectly formatted,
    // the cron schedule comparison will fail and the action will be logged as unknown (no action taken).
    const notificationCron = env.NOTIFICATION_CRON || "45 20 * * *";
    const teardownCron = env.TEARDOWN_CRON || "0 21 * * *";

    // Validate cron format (5 fields with valid ranges)
    function isValidCron(cron) {
      const parts = cron.trim().split(/\s+/);
      if (parts.length !== 5) return false;
      const ranges = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 7]];
      return parts.every((part, i) => {
        if (part === '*') return true;
        if (/^\*\/\d+$/.test(part)) return parseInt(part.slice(2)) >= 1 && parseInt(part.slice(2)) <= ranges[i][1];
        return part.split(',').every(v => {
          const m = v.match(/^(\d+)(?:-(\d+))?$/);
          if (!m) return false;
          const lo = parseInt(m[1]), hi = m[2] ? parseInt(m[2]) : lo;
          return lo >= ranges[i][0] && hi <= ranges[i][1] && lo <= hi;
        });
      });
    }
    if (!isValidCron(notificationCron) || !isValidCron(teardownCron)) {
      console.warn(`Invalid cron format detected - notification: ${notificationCron}, teardown: ${teardownCron}`);
      await logToD1(env.NEXUS_DB, 'warn', 'Invalid cron format in environment variables', {
        notificationCron,
        teardownCron
      });
    }

    if (cronSchedule === notificationCron) {
      // Notification cron triggered
      await logToD1(env.NEXUS_DB, 'info', 'Sending teardown notification email');
      await sendNotification(env, config);
    } else if (cronSchedule === teardownCron) {
      // Teardown cron triggered
      await logToD1(env.NEXUS_DB, 'warn', 'Triggering scheduled teardown');
      await triggerTeardown(env, config);
    } else {
      console.log(`Unknown cron schedule: ${cronSchedule} - no action taken`);
      await logToD1(env.NEXUS_DB, 'warn', 'Unknown cron schedule', { cron: cronSchedule });
    }
  } catch (error) {
    console.error('Error in scheduled teardown:', error);
    await logToD1(env.NEXUS_DB, 'error', 'Scheduled teardown error', {
      error: error.message,
      stack: error.stack?.substring(0, 500),
    });
  }
}

/**
 * Check infrastructure status via GitHub Actions API.
 * Returns the infra state: 'deployed', 'torn-down', 'offline', 'running', or 'unknown'.
 */
async function checkInfraStatus(env) {
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    console.warn('Missing GitHub env vars for status check');
    return 'unknown';
  }

  try {
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs?per_page=100`;
    const response = await fetchWithTimeout(url, {
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Scheduled-Teardown',
      },
    });

    if (!response.ok) {
      console.warn(`GitHub API returned ${response.status}, cannot determine infra state`);
      return 'unknown';
    }

    const data = await response.json();
    if (!data.workflow_runs || !Array.isArray(data.workflow_runs)) {
      return 'unknown';
    }

    const WORKFLOW_PATHS = {
      initialSetup: 'initial-setup.yaml',
      spinUp: 'spin-up.yml',
      teardown: 'teardown.yml',
      destroy: 'destroy-all.yml',
    };

    // Find the most recent run for each relevant workflow
    const workflows = { initialSetup: null, spinUp: null, teardown: null, destroy: null };

    for (const run of data.workflow_runs) {
      const path = run.path || '';
      const name = run.name || '';

      if (!workflows.initialSetup && (path.includes(WORKFLOW_PATHS.initialSetup) || name.includes('Initial Setup'))) {
        workflows.initialSetup = run;
      } else if (!workflows.spinUp && (path.includes(WORKFLOW_PATHS.spinUp) || name.includes('Spin Up') || name.includes('Spin-Up'))) {
        workflows.spinUp = run;
      } else if (!workflows.teardown && (path.includes(WORKFLOW_PATHS.teardown) || name.includes('Teardown'))) {
        workflows.teardown = run;
      } else if (!workflows.destroy && (path.includes(WORKFLOW_PATHS.destroy) || name.includes('Destroy'))) {
        workflows.destroy = run;
      }
    }

    // Check if any workflow is currently running
    const allRuns = [workflows.initialSetup, workflows.spinUp, workflows.teardown, workflows.destroy].filter(Boolean);
    const runningWorkflow = allRuns.find(r => r.status === 'in_progress' || r.status === 'queued');

    if (runningWorkflow) {
      return 'running';
    }

    // Find the most recent completed workflow (any conclusion, not just success)
    const completedRuns = allRuns
      .filter(r => r.status === 'completed')
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

    if (completedRuns.length > 0) {
      const lastRun = completedRuns[0];
      const lastPath = lastRun.path || '';
      const lastName = lastRun.name || '';
      const lastConclusion = lastRun.conclusion || '';

      if (lastPath.includes(WORKFLOW_PATHS.initialSetup) || lastName.includes('Initial Setup') ||
          lastPath.includes(WORKFLOW_PATHS.spinUp) || lastName.includes('Spin Up') || lastName.includes('Spin-Up')) {
        return 'deployed';
      } else if (lastPath.includes(WORKFLOW_PATHS.teardown) || lastName.includes('Teardown')) {
        // If teardown failed, infra is likely still deployed
        return lastConclusion === 'success' ? 'torn-down' : 'deployed';
      } else if (lastPath.includes(WORKFLOW_PATHS.destroy) || lastName.includes('Destroy')) {
        // If destroy failed, infra is at least torn down but not fully offline
        return lastConclusion === 'success' ? 'offline' : 'torn-down';
      }
    }

    return 'unknown';
  } catch (error) {
    console.warn('Failed to check infra status:', error.message);
    return 'unknown';
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
  // Check if silent mode is enabled (suppresses all automated emails)
  const silentMode = await getConfigValue(env.NEXUS_DB, 'silent_mode', 'false');
  if (silentMode === 'true') {
    await logToD1(env.NEXUS_DB, 'info', 'Silent mode enabled - skipping shutdown notification email');
    return;
  }

  // Check if shutdown notifications are enabled
  const notifyOnShutdown = await getConfigValue(env.NEXUS_DB, 'notify_on_shutdown', 'true');
  if (notifyOnShutdown !== 'true') {
    await logToD1(env.NEXUS_DB, 'info', 'Shutdown notification email disabled by user');
    return;
  }

  if (!env.RESEND_API_KEY || !env.ADMIN_EMAIL || !env.DOMAIN) {
    const missingVars = [];
    if (!env.RESEND_API_KEY) missingVars.push('RESEND_API_KEY');
    if (!env.ADMIN_EMAIL) missingVars.push('ADMIN_EMAIL');
    if (!env.DOMAIN) missingVars.push('DOMAIN');

    const message = `Missing required environment variables for notification: ${missingVars.join(', ')}`;
    console.log(message);
    await logToD1(env.NEXUS_DB, 'warn', message);
    return;
  }

  // Email recipients: User as primary, Admin + extra users in CC.
  // USER_EMAIL may be comma-separated. Validation via the Resend-accepted
  // email regex hoisted to module scope at the top of the file.
  const userEmails = (env.USER_EMAIL || '')
    .split(',')
    .map((e) => e.trim())
    .filter(isValidResendEmail);
  const userEmail = userEmails[0] || null;
  const extraUserEmails = userEmails.slice(1);

  try {
    const teardownTime = `${config.teardownTime} ${getTimezoneAbbr(config.timezone)}`;
    const controlPlaneUrl = safeHttpsUrl(env.CONTROL_PLANE_URL, `https://control.${env.DOMAIN}`);

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
          <li><a href="${controlPlaneUrl}" style="color:#00ff88">Control Plane</a> - Manage infrastructure</li>
          <li><a href="https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions" style="color:#00ff88">GitHub Actions</a> - View workflows</li>
        </ul>
        <div style="margin-top:2rem;padding:1rem;background:#1a1a2e;border-left:3px solid #ffaa00">
          <p style="color:#ffaa00;margin:0;font-weight:bold">📮 Do not reply</p>
          <p style="color:#999;margin:0.5rem 0 0 0;font-size:13px">This mailbox is not monitored. For questions or support, please contact: <a href="mailto:${env.ADMIN_EMAIL}" style="color:#00ff88">${env.ADMIN_EMAIL}</a></p>
        </div>
        <p style="color:#666;font-size:12px;margin-top:1rem">This is an automated reminder. Infrastructure will be torn down automatically unless disabled.</p>
      </div>
    `;

    // Resend requires the sender domain to be verified. On multi-tenant
    // deployments (e.g. an education / classroom admin panel), DOMAIN is a
    // per-user subdomain that isn't registered with Resend, but BASE_DOMAIN is the
    // shared parent that IS verified. Fall back to DOMAIN for single-stack
    // installs where BASE_DOMAIN isn't set.
    const fromDomain = env.BASE_DOMAIN || env.DOMAIN;
    const emailPayload = {
      from: `Nexus-Stack <nexus@${fromDomain}>`,
      to: userEmail ? [userEmail] : [env.ADMIN_EMAIL],
      subject: '⚠️ Scheduled Teardown in 15 Minutes',
      html: emailHtml,
    };
    if (userEmail) {
      emailPayload.cc = [env.ADMIN_EMAIL, ...extraUserEmails];
    }

    const response = await fetchWithTimeout('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(emailPayload),
    }, 15000);

    if (response.ok) {
      const ccList = emailPayload.cc || [];
      const recipientMsg = userEmail
        ? (ccList.length > 0 ? `${userEmail} (cc: ${ccList.join(', ')})` : userEmail)
        : env.ADMIN_EMAIL;
      const message = `Notification email sent to ${recipientMsg}`;
      console.log(`✅ ${message}`);
      await logToD1(env.NEXUS_DB, 'info', message);
    } else {
      const errorText = await response.text();
      const message = `Failed to send notification email: HTTP ${response.status}`;
      console.error(`⚠️ ${message} - ${errorText}`);
      await logToD1(env.NEXUS_DB, 'error', message, {
        status: response.status,
        error: errorText,
      });
    }
  } catch (error) {
    const message = 'Exception while sending notification email';
    console.error(`Error sending notification:`, error);
    await logToD1(env.NEXUS_DB, 'error', message, {
      error: error.message,
      stack: error.stack?.substring(0, 500),
    });
  }
}

async function triggerTeardown(env, config) {
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    const missingVars = [];
    if (!env.GITHUB_TOKEN) missingVars.push('GITHUB_TOKEN');
    if (!env.GITHUB_OWNER) missingVars.push('GITHUB_OWNER');
    if (!env.GITHUB_REPO) missingVars.push('GITHUB_REPO');

    const message = `Missing required environment variables for teardown: ${missingVars.join(', ')}`;
    console.log(message);
    await logToD1(env.NEXUS_DB, 'error', message);
    return;
  }

  try {
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/teardown.yml/dispatches`;

    const response = await fetchWithTimeout(url, {
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
      const message = 'Teardown workflow triggered successfully';
      console.log(`✅ ${message}`);
      await logToD1(env.NEXUS_DB, 'info', message, {
        owner: env.GITHUB_OWNER,
        repo: env.GITHUB_REPO,
      });
    } else {
      const errorText = await response.text();
      const message = `Failed to trigger teardown workflow: HTTP ${response.status}`;
      console.error(`⚠️ ${message} - ${errorText}`);
      await logToD1(env.NEXUS_DB, 'error', message, {
        status: response.status,
        error: errorText,
        owner: env.GITHUB_OWNER,
        repo: env.GITHUB_REPO,
      });
    }
  } catch (error) {
    const message = 'Exception while triggering teardown';
    console.error(`Error triggering teardown:`, error);
    await logToD1(env.NEXUS_DB, 'error', message, {
      error: error.message,
      stack: error.stack?.substring(0, 500),
    });
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
