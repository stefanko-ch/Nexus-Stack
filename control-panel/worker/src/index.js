/**
 * Scheduled Teardown Worker
 * 
 * Runs daily to check if scheduled teardown is enabled and triggers:
 * 1. Email notification (15 minutes before teardown)
 * 2. Teardown workflow (at configured time)
 * 
 * Configuration stored in KV: SCHEDULED_TEARDOWN
 * - enabled: "true" | "false"
 * - timezone: "Europe/Zurich" (default)
 * - teardown_time: "22:00" (default)
 * - notification_time: "21:45" (default, 15 min before)
 */

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
    // Get configuration from KV
    const config = await getConfig(env.SCHEDULED_TEARDOWN);
    
    if (!config.enabled || config.enabled !== 'true') {
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
        await env.SCHEDULED_TEARDOWN.delete('delay_until');
        console.log('Delay period expired, teardown will proceed');
      }
    }

    const now = new Date();
    const currentTime = now.toISOString();
    const cronTime = event.cron; // e.g., "0 21 * * *"
    
    console.log(`Scheduled event triggered at ${currentTime} (cron: ${cronTime})`);

    // Determine if this is notification time or teardown time
    const hour = now.getUTCHours();
    const minute = now.getUTCMinutes();
    
    // Notification runs at 20:45 UTC (21:45 CET) = 15 min before 21:00 UTC (22:00 CET)
    // Teardown runs at 21:00 UTC (22:00 CET)
    if (hour === 20 && minute === 45) {
      await sendNotification(env, config);
    } else if (hour === 21 && minute === 0) {
      await triggerTeardown(env, config);
    }
  } catch (error) {
    console.error('Error in scheduled teardown:', error);
  }
}

async function getConfig(kv) {
  const enabled = await kv.get('enabled') || 'false';
  const timezone = await kv.get('timezone') || 'Europe/Zurich';
  const teardownTime = await kv.get('teardown_time') || '22:00';
  const notificationTime = await kv.get('notification_time') || '21:45';
  const delayUntil = await kv.get('delay_until') || null;
  
  return { enabled, timezone, teardownTime, notificationTime, delayUntil };
}

async function sendNotification(env, config) {
  if (!env.RESEND_API_KEY || !env.ADMIN_EMAIL || !env.DOMAIN) {
    console.log('Missing required environment variables for notification');
    return;
  }

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
            <li>Control Panel will remain active for re-deployment</li>
            <li>All data and state will be preserved</li>
          </ul>
        </div>
        <h2 style="color:#00ff88;margin-top:2rem">🛑 Want to prevent teardown?</h2>
        <p style="color:#fff">You can disable scheduled teardown via the Control Panel settings.</p>
        <h2 style="color:#00ff88;margin-top:2rem">🔗 Quick Links</h2>
        <ul>
          <li><a href="https://control.${env.DOMAIN}" style="color:#00ff88">Control Panel</a> - Manage infrastructure</li>
          <li><a href="https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions" style="color:#00ff88">GitHub Actions</a> - View workflows</li>
        </ul>
        <div style="margin-top:2rem;padding:1rem;background:#1a1a2e;border-left:3px solid #ffaa00">
          <p style="color:#ffaa00;margin:0;font-weight:bold">📮 Do not reply</p>
          <p style="color:#999;margin:0.5rem 0 0 0;font-size:13px">This mailbox is not monitored. For questions or support, please contact: <a href="mailto:${env.ADMIN_EMAIL}" style="color:#00ff88">${env.ADMIN_EMAIL}</a></p>
        </div>
        <p style="color:#666;font-size:12px;margin-top:1rem">This is an automated reminder. Infrastructure will be torn down automatically unless disabled.</p>
      </div>
    `;

    const response = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: `Nexus-Stack <nexus@${env.DOMAIN}>`,
        to: [env.ADMIN_EMAIL],
        subject: '⚠️ Scheduled Teardown in 15 Minutes',
        html: emailHtml,
      }),
    });

    if (response.ok) {
      console.log(`✅ Notification email sent to ${env.ADMIN_EMAIL}`);
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

function getTimezoneAbbr(timezone) {
  // Simple timezone abbreviation mapping
  const tzMap = {
    'Europe/Zurich': 'CET',
    'America/New_York': 'EST',
    'America/Los_Angeles': 'PST',
  };
  return tzMap[timezone] || 'UTC';
}
