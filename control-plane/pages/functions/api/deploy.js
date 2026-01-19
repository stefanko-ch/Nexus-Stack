/**
 * Trigger Setup Control Plane workflow
 * POST /api/deploy (legacy endpoint name for backward compatibility)
 * 
 * Triggers the GitHub Actions setup-control-plane.yaml workflow.
 * Includes validation, error handling, and retry logic.
 */

import { logApiCall, logError } from './_utils/logger.js';

export async function onRequestPost(context) {
  const { env, request } = context;
  
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

  // Log the API call
  await logApiCall(env.NEXUS_DB, '/api/deploy', 'POST', {
    action: 'trigger_setup_control_plane',
  });

  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/setup-control-plane.yaml/dispatches`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Plane',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main' }),
    });

    // GitHub returns 204 No Content on success
    if (response.status === 204) {
      return new Response(JSON.stringify({ 
        success: true, 
        message: 'Deploy workflow triggered successfully' 
      }), {
        status: 200,
        headers: { 
          'Content-Type': 'application/json',
        },
      });
    }

    // Handle errors
    const errorText = await response.text();
    let errorMessage = `Failed to trigger workflow: ${response.status}`;
    
    try {
      const errorJson = JSON.parse(errorText);
      errorMessage = errorJson.message || errorMessage;
    } catch {
      // If error is not JSON, use the text as-is
      if (errorText) {
        errorMessage = errorText.substring(0, 200); // Limit length
      }
    }

    console.error(`Deploy trigger failed: ${response.status} - ${errorMessage}`);

    return new Response(JSON.stringify({ 
      success: false, 
      error: errorMessage 
    }), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Deploy endpoint error:', error);
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Network error while triggering workflow' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
