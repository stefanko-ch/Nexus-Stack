/**
 * Get Nexus-Stack version from GitHub releases
 * GET /api/version
 * 
 * Returns the latest release version from GitHub
 */
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
    // Fetch the latest release from GitHub
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/releases/latest`;
    
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Plane',
      },
    });

    if (!response.ok) {
      // If no releases exist yet, return a default version
      if (response.status === 404) {
        return new Response(JSON.stringify({
          success: true,
          version: 'dev',
          name: 'Development',
          url: `https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}`,
          publishedAt: null,
        }), {
          headers: { 
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=300', // 300s = 5 minutes
          },
        });
      }
      
      const errorText = await response.text();
      console.error(`GitHub API error: ${response.status} - ${errorText}`);
      
      return new Response(JSON.stringify({ 
        success: false, 
        error: `Failed to fetch version: ${response.status}` 
      }), {
        status: response.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const release = await response.json();

    return new Response(JSON.stringify({
      success: true,
      version: release.tag_name,
      name: release.name || release.tag_name,
      url: release.html_url,
      publishedAt: release.published_at,
    }), {
      headers: { 
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300', // 300s = 5 minutes
      },
    });
  } catch (error) {
    console.error('Version endpoint error:', error);
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Internal server error' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
