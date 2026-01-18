/**
 * Trigger Spin-Up workflow
 * POST /api/spin-up
 * 
 * Triggers the GitHub Actions spin-up.yml workflow.
 * Reads enabled services from D1 and passes them to the workflow.
 */

// D1 Helper Functions
async function getEnabledServicesFromD1(db) {
  try {
    const results = await db.prepare('SELECT name, enabled FROM services').all();
    const map = {};
    for (const row of results.results || []) {
      map[row.name] = row.enabled === 1;
    }
    return map;
  } catch {
    return {};
  }
}

function decodeBase64(input) {
  if (typeof atob === 'function') {
    return atob(input);
  }
  return Buffer.from(input, 'base64').toString('utf-8');
}

/**
 * Parse services.tfvars to extract service definitions
 */
function parseServicesConfig(content) {
  const services = [];
  const lines = content.split('\n');
  let current = null;
  let inBlock = false;

  for (const line of lines) {
    const serviceMatch = line.match(/^\s*([a-zA-Z0-9-]+)\s*=\s*\{\s*$/);
    if (serviceMatch) {
      current = { name: serviceMatch[1], defaultEnabled: false };
      inBlock = true;
      continue;
    }

    if (inBlock && current) {
      const enabledMatch = line.match(/^\s*enabled\s*=\s*(true|false)\s*$/);
      if (enabledMatch) {
        current.defaultEnabled = enabledMatch[1] === 'true';
      }
      if (line.trim() === '}') {
        services.push(current);
        current = null;
        inBlock = false;
      }
    }
  }

  return services;
}

/**
 * Fetch services.tfvars from GitHub
 */
async function fetchServicesFile(env) {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/tofu/services.tfvars`;
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'Nexus-Stack-Control-Plane',
    },
  });

  if (!response.ok) {
    throw new Error(`GitHub API error: ${response.status}`);
  }

  return response.json();
}

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

  try {
    // Get enabled services from D1
    let enabledServicesList = [];
    
    if (env.NEXUS_DB) {
      // Fetch service definitions from GitHub
      const file = await fetchServicesFile(env);
      const content = decodeBase64(file.content || '');
      const serviceDefinitions = parseServicesConfig(content);
      
      // Get enabled status from D1
      const enabledMap = await getEnabledServicesFromD1(env.NEXUS_DB);
      
      // Build list of enabled services (D1 value or default)
      enabledServicesList = serviceDefinitions
        .filter(svc => {
          if (Object.hasOwn(enabledMap, svc.name)) {
            return enabledMap[svc.name];
          }
          return svc.defaultEnabled;
        })
        .map(svc => svc.name);
    }

    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/spin-up.yml/dispatches`;
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Plane',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        ref: 'main',
        inputs: {
          enabled_services: enabledServicesList.join(',')
        }
      }),
    });

    if (response.status === 204) {
      return new Response(JSON.stringify({ 
        success: true, 
        message: 'Spin-up workflow triggered successfully',
        enabledServices: enabledServicesList
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
      error: error.message || 'Network error while triggering workflow' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
