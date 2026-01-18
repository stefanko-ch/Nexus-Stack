/**
 * Send infrastructure credentials via email
 * POST /api/send-credentials
 * 
 * Reads credentials from CREDENTIALS_JSON secret and sends them via Resend.
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

  // Check for credentials secret
  if (!env.CREDENTIALS_JSON) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Credentials secret not configured'
    }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }

  try {
    // Get credentials from secret (already JSON string)
    const credentialsJson = env.CREDENTIALS_JSON;
    
    if (!credentialsJson) {
      return new Response(JSON.stringify({
        success: false,
        error: 'No credentials found. Deploy the stack first.'
      }), { status: 404, headers: { 'Content-Type': 'application/json' } });
    }

    const credentials = JSON.parse(credentialsJson);
    const domain = env.DOMAIN;
    const adminEmail = env.ADMIN_EMAIL;
    const userEmail = env.USER_EMAIL && env.USER_EMAIL.trim() !== '' ? env.USER_EMAIL : null;

    // Only send Infisical credentials - all other credentials are stored in Infisical
    if (!credentials.infisical_admin_password) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Infisical credentials not found. Deploy the stack first.'
      }), { status: 404, headers: { 'Content-Type': 'application/json' } });
    }

    // Build email HTML - only Infisical + hint to check Infisical for other passwords
    const emailHTML = `
<div style="font-family:monospace;background:#0a0a0f;color:#00ff88;padding:20px;max-width:600px">
  <h1 style="color:#00ff88;margin-top:0">🔐 Nexus-Stack Credentials</h1>
  
  <p style="color:#ccc">Your Nexus-Stack is ready at <strong style="color:#fff">${domain}</strong></p>
  
  <h2 style="color:#00ff88;font-size:16px;margin-top:24px">🔑 Infisical (Secret Manager)</h2>
  <div style="background:#1a1a2e;padding:12px;margin:8px 0;border-radius:4px;border-left:3px solid #00ff88">
    <div style="color:#ccc;font-size:14px">
      <div>URL: <a href="https://infisical.${domain}" style="color:#00ff88">https://infisical.${domain}</a></div>
      <div>Email: <span style="color:#fff">${adminEmail}</span></div>
      <div>Password: <span style="color:#fff;font-family:monospace">${credentials.infisical_admin_password}</span></div>
    </div>
  </div>
  
  <div style="background:#1a2e1a;padding:12px;margin:20px 0;border-radius:4px;border-left:3px solid #00ff88">
    <div style="color:#00ff88;font-weight:bold">📦 Other Service Credentials</div>
    <div style="color:#ccc;font-size:14px;margin-top:8px">
      All service credentials (Grafana, Portainer, etc.) are stored in Infisical.<br>
      Log in to Infisical to view them.
    </div>
  </div>
  
  <div style="background:#2d1f1f;padding:12px;margin:20px 0;border-radius:4px;border-left:3px solid #ff6b6b">
    <div style="color:#ff6b6b;font-weight:bold">⚠️ Security Notice</div>
    <div style="color:#ccc;font-size:14px;margin-top:8px">
      <ul style="margin:0;padding-left:20px">
        <li>Store the Infisical password in a password manager</li>
        <li>Change passwords after first login</li>
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

    // Send email via Resend (User as primary, Admin in CC)
    const emailPayload = {
      from: `Nexus-Stack <nexus@${domain}>`,
      to: userEmail ? [userEmail] : [adminEmail],
      subject: '🔐 Nexus-Stack Credentials',
      html: emailHTML
    };
    if (userEmail) {
      emailPayload.cc = [adminEmail];
    }

    const resendResponse = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(emailPayload)
    });

    if (!resendResponse.ok) {
      const error = await resendResponse.json();
      throw new Error(`Resend API error: ${error.message || JSON.stringify(error)}`);
    }

    const emailResult = await resendResponse.json();

    const recipientMsg = userEmail ? `${userEmail} (cc: ${adminEmail})` : adminEmail;
    return new Response(JSON.stringify({
      success: true,
      message: `Credentials sent to ${recipientMsg}`,
      emailId: emailResult.id
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
