/**
 * Trigger Destroy All workflow
 * POST /api/destroy
 */
export async function onRequestPost(context) {
  const { env } = context;
  
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/destroy-all.yml/dispatches`;
  
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
        confirm: 'DESTROY'
      }
    }),
  });

  if (response.status === 204) {
    return new Response(JSON.stringify({ 
      success: true, 
      message: 'Destroy workflow triggered successfully' 
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const error = await response.text();
  return new Response(JSON.stringify({ 
    success: false, 
    error: `Failed to trigger workflow: ${error}` 
  }), {
    status: response.status,
    headers: { 'Content-Type': 'application/json' },
  });
}
