/**
 * Manage services configuration
 * GET /api/services - Get all services with enabled/deployed status
 * POST /api/services - Enable/disable a service (staged in D1, not deployed)
 * 
 * Service definitions come from tofu/services.tfvars (read-only)
 * Service state is stored in Cloudflare D1 database (services table):
 *   - enabled: what the user wants (staged state)
 *   - deployed: what is currently running
 */

import { logApiCall, logError } from './_utils/logger.js';

// D1 Helper Functions

/**
 * Get service states from D1 (both enabled and deployed)
 * Returns: { serviceName: { enabled: bool, deployed: bool }, ... }
 */
async function getServiceStatesFromD1(db) {
  try {
    const results = await db.prepare('SELECT name, enabled, deployed FROM services').all();
    const map = {};
    for (const row of results.results || []) {
      map[row.name] = {
        enabled: row.enabled === 1,
        deployed: row.deployed === 1,
      };
    }
    return map;
  } catch {
    return {};
  }
}

/**
 * Set service enabled state (staged, not deployed yet)
 */
async function setServiceEnabled(db, name, enabled) {
  // Get current deployed state to preserve it
  const current = await db.prepare('SELECT deployed FROM services WHERE name = ?').bind(name).first();
  const deployed = current ? current.deployed : 0;
  
  await db.prepare(
    'INSERT OR REPLACE INTO services (name, enabled, deployed, updated_at) VALUES (?, ?, ?, datetime("now"))'
  ).bind(name, enabled ? 1 : 0, deployed).run();
}

function decodeBase64(input) {
  if (typeof atob === 'function') {
    return atob(input);
  }
  return Buffer.from(input, 'base64').toString('utf-8');
}

/**
 * Parse services.tfvars to extract service definitions
 * The 'enabled' field in tfvars is used as the DEFAULT value only
 */
function parseServicesConfig(content) {
  const services = [];
  const lines = content.split('\n');
  let current = null;
  let inBlock = false;

  for (const line of lines) {
    const serviceMatch = line.match(/^\s*([a-zA-Z0-9-]+)\s*=\s*\{\s*$/);
    if (serviceMatch) {
      current = { 
        name: serviceMatch[1], 
        defaultEnabled: false,
        core: false, 
        subdomain: '',
        port: 0,
        public: false,
        description: '' 
      };
      inBlock = true;
      continue;
    }

    if (inBlock && current) {
      // Parse enabled (used as default)
      const enabledMatch = line.match(/^\s*enabled\s*=\s*(true|false)\s*$/);
      if (enabledMatch) {
        current.defaultEnabled = enabledMatch[1] === 'true';
      }

      // Parse core
      const coreMatch = line.match(/^\s*core\s*=\s*(true|false)\s*$/);
      if (coreMatch) {
        current.core = coreMatch[1] === 'true';
      }

      // Parse subdomain
      const subdomainMatch = line.match(/^\s*subdomain\s*=\s*"(.*)"\s*$/);
      if (subdomainMatch) {
        current.subdomain = subdomainMatch[1];
      }

      // Parse port
      const portMatch = line.match(/^\s*port\s*=\s*(\d+)\s*$/);
      if (portMatch) {
        current.port = parseInt(portMatch[1], 10);
      }

      // Parse public
      const publicMatch = line.match(/^\s*public\s*=\s*(true|false)\s*$/);
      if (publicMatch) {
        current.public = publicMatch[1] === 'true';
      }

      // Parse description
      const descriptionMatch = line.match(/^\s*description\s*=\s*"(.*)"\s*$/);
      if (descriptionMatch) {
        current.description = descriptionMatch[1];
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
    const errorText = await response.text();
    throw new Error(`GitHub API error (${response.status}): ${errorText.substring(0, 200)}`);
  }

  return response.json();
}

/**
 * GET /api/services
 * Returns all services with their enabled and deployed status
 */
export async function onRequestGet(context) {
  const { env } = context;

  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Missing required environment variables (GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO)',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    // Fetch service definitions from GitHub
    const file = await fetchServicesFile(env);
    const content = decodeBase64(file.content || '');
    const serviceDefinitions = parseServicesConfig(content);

    // Fetch service states from D1
    const stateMap = env.NEXUS_DB ? await getServiceStatesFromD1(env.NEXUS_DB) : {};

    // Merge: use D1 values if exist, otherwise use defaults from tfvars
    let pendingChangesCount = 0;
    const services = serviceDefinitions.map(svc => {
      const state = stateMap[svc.name];
      const enabled = state ? state.enabled : svc.defaultEnabled;
      const deployed = state ? state.deployed : svc.defaultEnabled;
      const hasPendingChange = enabled !== deployed;
      
      if (hasPendingChange) {
        pendingChangesCount++;
      }

      return {
        name: svc.name,
        subdomain: svc.subdomain,
        port: svc.port,
        public: svc.public,
        core: svc.core,
        description: svc.description,
        enabled,      // What user wants (staged)
        deployed,     // What is currently running
        pending: hasPendingChange,
      };
    });

    return new Response(JSON.stringify({
      success: true,
      services,
      pendingChangesCount,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services GET error:', error);
    await logError(env.NEXUS_DB, '/api/services', 'GET', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to load services',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

/**
 * POST /api/services
 * Enable/disable a service (saves to D1 only, no deployment)
 * Use the Spin Up button to deploy changes
 */
export async function onRequestPost(context) {
  const { env, request } = context;

  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Missing required environment variables',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured. Re-run the deploy workflow to set up D1 bindings.',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const body = await request.json();
    const serviceName = body.service;
    const enabled = body.enabled;

    if (!serviceName || typeof enabled !== 'boolean') {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid payload. Expected { service: string, enabled: boolean }',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Fetch service definitions to validate and check core status
    const file = await fetchServicesFile(env);
    const content = decodeBase64(file.content || '');
    const serviceDefinitions = parseServicesConfig(content);
    const targetService = serviceDefinitions.find(s => s.name === serviceName);

    if (!targetService) {
      return new Response(JSON.stringify({
        success: false,
        error: `Service not found: ${serviceName}`,
      }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Block disabling core services
    if (targetService.core && !enabled) {
      return new Response(JSON.stringify({
        success: false,
        error: `Cannot disable ${serviceName} - it is a core service required for Nexus Stack operation`,
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Save to D1 (staged, not deployed yet)
    await setServiceEnabled(env.NEXUS_DB, serviceName, enabled);

    // Log the service toggle
    await logApiCall(env.NEXUS_DB, '/api/services', 'POST', {
      action: 'toggle_service',
      service: serviceName,
      enabled: enabled,
    });

    // Get updated state for response
    const stateMap = await getServiceStatesFromD1(env.NEXUS_DB);
    let pendingChangesCount = 0;
    
    for (const svc of serviceDefinitions) {
      const state = stateMap[svc.name];
      if (state && state.enabled !== state.deployed) {
        pendingChangesCount++;
      }
    }

    return new Response(JSON.stringify({
      success: true,
      message: `Service ${serviceName} ${enabled ? 'enabled' : 'disabled'}. Click "Spin Up" to deploy changes.`,
      pendingChangesCount,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services POST error:', error);
    await logError(env.NEXUS_DB, '/api/services', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to update service',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
