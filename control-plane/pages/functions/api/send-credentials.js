/**
 * Send infrastructure credentials via email
 * POST /api/send-credentials
 * 
 * Sends Infisical credentials and other service passwords to admin email
 */

export async function onRequestPost(context) {
  const { env, request } = context;

  // Validate environment variables
  const requiredEnv = ['GITHUB_OWNER', 'GITHUB_REPO', 'GITHUB_TOKEN', 'RESEND_API_KEY'];
  const missing = requiredEnv.filter(key => !env[key]);
  
  if (missing.length > 0) {
    return new Response(JSON.stringify({
      success: false,
      error: `Missing environment variables: ${missing.join(', ')}`
    }), { status: 400, headers: { 'Content-Type': 'application/json' } });
  }

  try {
    const adminEmail = env.ADMIN_EMAIL || '';
    
    if (!adminEmail) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Admin email not configured'
      }), { status: 400, headers: { 'Content-Type': 'application/json' } });
    }

    // Get secrets from GitHub
    let infisicalPassword = '';
    let otherSecrets = '';

    try {
      const secretsUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/secrets`;
      const secretsResponse = await fetch(secretsUrl, {
        headers: {
          'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github.v3+json'
        }
      });

      if (secretsResponse.ok) {
        const secretsData = await secretsResponse.json();
        const secretNames = secretsData.secrets ? secretsData.secrets.map(s => s.name) : [];
        
        // Get Infisical password from GitHub Actions output or environment
        if (secretNames.includes('INFISICAL_PASSWORD')) {
          infisicalPassword = '(Stored in GitHub Secrets)';
        }
        
        // List other relevant secrets
        const relevantSecrets = secretNames.filter(name => 
          ['HCLOUD_TOKEN', 'CLOUDFLARE_API_TOKEN', 'TF_VAR_', 'ADMIN_'].includes(
            name.substring(0, Math.min(name.length, 12))
          )
        );
        
        if (relevantSecrets.length > 0) {
          otherSecrets = `\n\nOther configured secrets:\n${relevantSecrets.map(s => `• ${s}`).join('\n')}`;
        }
      }
    } catch (error) {
      console.log('Could not fetch GitHub secrets:', error.message);
      infisicalPassword = '(Check GitHub Secrets)';
    }

    // Prepare email content
    const emailSubject = 'Nexus-Stack: Infrastructure Credentials';
    const emailHTML = `
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: 'Courier New', monospace; color: #333; line-height: 1.6; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #0a0a0f; color: #00ff88; padding: 20px; text-align: center; border-radius: 4px; }
        .header h1 { margin: 0; font-size: 24px; }
        .content { background: #f5f5f5; padding: 20px; margin-top: 20px; border-left: 4px solid #00ff88; }
        .credentials { background: white; padding: 15px; margin: 15px 0; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; }
        .section-title { font-weight: bold; color: #0a0a0f; margin-top: 15px; margin-bottom: 8px; }
        .footer { text-align: center; color: #999; font-size: 12px; margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; }
        .warning { background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 4px; margin: 15px 0; color: #856404; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 Nexus-Stack Credentials</h1>
        </div>
        
        <div class="content">
            <p>Hello,</p>
            
            <p>Here is a summary of your Nexus-Stack infrastructure credentials. Please keep this information safe.</p>
            
            <div class="section-title">📦 Infisical Credentials:</div>
            <div class="credentials">
                <p><strong>Username:</strong> admin</p>
                <p><strong>Password:</strong> ${infisicalPassword || '(Not configured - check GitHub Secrets)'}</p>
                <p><strong>Access:</strong> https://infisical.${env.DOMAIN || 'your-domain.com'}</p>
            </div>
            
            <div class="warning">
                ⚠️ <strong>Important:</strong> Keep your credentials secure. Do not share this email. Store sensitive information in a password manager.
            </div>
            
            ${otherSecrets}
            
            <div class="section-title">📖 Next Steps:</div>
            <ul>
                <li>Store these credentials securely</li>
                <li>Use Infisical to manage your infrastructure secrets</li>
                <li>Never commit credentials to Git</li>
            </ul>
            
            <div class="footer">
                <p>Built with ❤️ and lots of ☕️ by <a href="https://github.com/stefanko-ch" style="color: #00ff88; text-decoration: none;">Stefan</a></p>
                <p style="margin-top: 10px; color: #666;">
                    <a href="https://github.com/stefanko-ch/Nexus-Stack" style="color: #00ff88; text-decoration: none;">Nexus-Stack</a> • 
                    <a href="https://infisical.com" style="color: #00ff88; text-decoration: none;">Infisical</a>
                </p>
            </div>
        </div>
    </div>
</body>
</html>
    `;

    // Send email via Resend
    const resendResponse = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        from: env.RESEND_FROM_EMAIL || 'onboarding@resend.dev',
        to: adminEmail,
        subject: emailSubject,
        html: emailHTML
      })
    });

    if (!resendResponse.ok) {
      const error = await resendResponse.json();
      throw new Error(`Resend API error: ${error.message || 'Unknown error'}`);
    }

    const emailResult = await resendResponse.json();

    return new Response(JSON.stringify({
      success: true,
      message: 'Credentials email sent successfully',
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
