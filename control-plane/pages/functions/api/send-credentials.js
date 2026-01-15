/**
 * Send infrastructure credentials via email
 * POST /api/send-credentials
 * 
 * Reads credentials from KV (stored during deployment) and sends them via Resend.
 * Email matches the style of the "Stack Online" notification.
 */

export async function onRequestPost(context) {
  const { env } = context;

  // Validate environment variables
  const requiredEnv = ['RESEND_API_KEY', 'ADMIN_EMAIL', 'DOMAIN'];
  const missing = requiredEnv.filter(key => !env[key]);
  
  if (missing.length > 0) {
    return new Response(JSON.stringify({
      success: false,
      error: `Missing environment variables: ${missing.join(', ')}`
    }), { status: 400, headers: { 'Content-Type': 'application/json' } });
  }

  // Check KV namespace
  if (!env.SCHEDULED_TEARDOWN) {
    return new Response(JSON.stringify({
      success: false,
      error: 'KV namespace not configured'
    }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }

  try {
    // Get credentials from KV
    const credentialsJson = await env.SCHEDULED_TEARDOWN.get('credentials');
    
    if (!credentialsJson) {
      return new Response(JSON.stringify({
        success: false,
        error: 'No credentials found in KV. Deploy the stack first.'
      }), { status: 404, headers: { 'Content-Type': 'application/json' } });
    }

    const credentials = JSON.parse(credentialsJson);
    const domain = env.DOMAIN;
    const adminEmail = env.ADMIN_EMAIL;

    // Build credentials list for enabled services
    const serviceCredentials = [];
    
    if (credentials.infisical_admin_password) {
      serviceCredentials.push({
        name: 'Infisical',
        url: `https://infisical.${domain}`,
        username: credentials.admin_username || 'admin',
        password: credentials.infisical_admin_password
      });
    }
    
    if (credentials.grafana_admin_password) {
      serviceCredentials.push({
        name: 'Grafana',
        url: `https://grafana.${domain}`,
        username: 'admin',
        password: credentials.grafana_admin_password
      });
    }
    
    if (credentials.portainer_admin_password) {
      serviceCredentials.push({
        name: 'Portainer',
        url: `https://portainer.${domain}`,
        username: 'admin',
        password: credentials.portainer_admin_password
      });
    }
    
    if (credentials.kuma_admin_password) {
      serviceCredentials.push({
        name: 'Uptime Kuma',
        url: `https://uptime-kuma.${domain}`,
        username: 'admin',
        password: credentials.kuma_admin_password
      });
    }
    
    if (credentials.kestra_admin_password) {
      serviceCredentials.push({
        name: 'Kestra',
        url: `https://kestra.${domain}`,
        username: 'admin',
        password: credentials.kestra_admin_password
      });
    }
    
    if (credentials.n8n_admin_password) {
      serviceCredentials.push({
        name: 'n8n',
        url: `https://n8n.${domain}`,
        username: adminEmail,
        password: credentials.n8n_admin_password
      });
    }

    // Build HTML for credentials - same style as Stack Online email
    const credentialsHtml = serviceCredentials.map(svc => `
      <div style="background:#1a1a2e;padding:12px;margin:8px 0;border-radius:4px;border-left:3px solid #00ff88">
        <div style="color:#00ff88;font-weight:bold;margin-bottom:8px">${svc.name}</div>
        <div style="color:#ccc;font-size:14px">
          <div>URL: <a href="${svc.url}" style="color:#00ff88">${svc.url}</a></div>
          <div>Username: <span style="color:#fff">${svc.username}</span></div>
          <div>Password: <span style="color:#fff;font-family:monospace">${svc.password}</span></div>
        </div>
      </div>
    `).join('');

    // Build email HTML - matching Stack Online style
    const emailHTML = `
<div style="font-family:monospace;background:#0a0a0f;color:#00ff88;padding:20px;max-width:600px">
  <h1 style="color:#00ff88;margin-top:0">🔐 Nexus-Stack Credentials</h1>
  
  <p style="color:#ccc">Here are your service credentials for <strong style="color:#fff">${domain}</strong></p>
  
  <h2 style="color:#00ff88;font-size:16px;margin-top:24px">📦 Service Credentials</h2>
  ${credentialsHtml}
  
  <div style="background:#2d1f1f;padding:12px;margin:20px 0;border-radius:4px;border-left:3px solid #ff6b6b">
    <div style="color:#ff6b6b;font-weight:bold">⚠️ Security Notice</div>
    <div style="color:#ccc;font-size:14px;margin-top:8px">
      <ul style="margin:0;padding-left:20px">
        <li>Store these credentials in a password manager</li>
        <li>Change passwords after first login</li>
        <li>Never commit credentials to Git</li>
        <li>Delete this email after saving credentials</li>
      </ul>
    </div>
  </div>
  
  <h2 style="color:#00ff88;font-size:16px;margin-top:24px">🔗 Quick Links</h2>
  <ul style="color:#ccc;padding-left:20px">
    <li><a href="https://info.${domain}" style="color:#00ff88">Info Page</a> - All services overview</li>
    <li><a href="https://control.${domain}" style="color:#00ff88">Control Plane</a> - Manage infrastructure</li>
  </ul>
  
  <p style="color:#666;font-size:12px;margin-top:24px;border-top:1px solid #333;padding-top:16px">
    Sent from Nexus-Stack • <a href="https://github.com/stefanko-ch/Nexus-Stack" style="color:#00ff88">GitHub</a>
  </p>
</div>
    `;

    // Send email via Resend
    const resendResponse = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        from: `Nexus-Stack <nexus@${domain}>`,
        to: [adminEmail],
        subject: '🔐 Nexus-Stack Credentials',
        html: emailHTML
      })
    });

    if (!resendResponse.ok) {
      const error = await resendResponse.json();
      throw new Error(`Resend API error: ${error.message || JSON.stringify(error)}`);
    }

    const emailResult = await resendResponse.json();

    return new Response(JSON.stringify({
      success: true,
      message: `Credentials sent to ${adminEmail}`,
      emailId: emailResult.id,
      servicesIncluded: serviceCredentials.map(s => s.name)
    }), { 
      status: 200, 
      headers: { 'Content-Type': 'application/json' } 
    });

  } catch (error) {
    console.error('Failed to send credentials email:', error);
    return new Response(JSON.stringify({
      success: false,
      error: `Failed to send email: ${error.message}`
    }), { 
      status: 500, 
      headers: { 'Content-Type': 'application/json' } 
    });
  }
}
