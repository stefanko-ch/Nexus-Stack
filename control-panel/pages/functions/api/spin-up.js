/**
 * Trigger Spin-Up workflow
 * POST /api/spin-up
 * 
 * Triggers the GitHub Actions spin-up.yml workflow.
 * Includes validation and error handling.
 */
export async function onRequestPost(context) {
  const { env } = context;
  
  // Validate environment variables
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Missing required environment variables' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/spin-up.yml/dispatches`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Panel',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        ref: 'main',
        inputs: {
          send_credentials: 'false'
        }
      }),
    });

    if (response.status === 204) {
      return new Response(JSON.stringify({ 
        success: true, 
        message: 'Spin-up workflow triggered successfully' 
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const errorText = await response.text();
    let errorMessage = `Failed to trigger workflow: ${response.status}`;
    
    try {
      const errorJson = JSON.parse(errorText);
      errorMessage = errorJson.message || errorMessage;
    } catch {
      if (errorText) {
        errorMessage = errorText.substring(0, 200);
      }
    }

    console.error(`Spin-up trigger failed: ${response.status} - ${errorMessage}`);

    return new Response(JSON.stringify({ 
      success: false, 
      error: errorMessage 
    }), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Spin-up endpoint error:', error);
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Network error while triggering workflow' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
