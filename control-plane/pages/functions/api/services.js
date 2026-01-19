/**
 * Manage services configuration
 * GET /api/services - Get all services with their enabled status
 * POST /api/services - Enable/disable a service (stored in D1)
 * 
 * Service definitions come from tofu/services.tfvars (read-only)
 * Enabled status is stored in Cloudflare D1 database (services table)
 */

import { logApiCall, logError } from './_utils/logger.js';

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

async function setServiceEnabled(db, name, enabled) {
  await db.prepare('INSERT OR REPLACE INTO services (name, enabled, updated_at) VALUES (?, ?, datetime("now"))').bind(name, enabled ? 1 : 0).run();
}

function decodeBase64(input) {
  if (typeof atob === 'function') {
    return atob(input);
  }
  return Buffer.from(input, 'base64').toString('utf-8');
}

/**
 * Parse services.tfvars to extract service definitions
 * Now only reads: subdomain, port, public, core, description
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
 * Trigger spin-up workflow with enabled services list
 */
async function triggerSpinUp(env, enabledServices) {
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
        enabled_services: enabledServices.join(',')
      }
    }),
  });

  if (response.status !== 204) {
    const errorText = await response.text();
    throw new Error(`Failed to trigger spin-up (${response.status}): ${errorText.substring(0, 200)}`);
  }
}

/**
 * GET /api/services
 * Returns all services with their current enabled status
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

    // Fetch enabled status from D1
    const enabledMap = env.NEXUS_DB ? await getEnabledServicesFromD1(env.NEXUS_DB) : {};

    // Merge: use D1 value if exists, otherwise use default from tfvars
    const services = serviceDefinitions.map(svc => ({
      name: svc.name,
      subdomain: svc.subdomain,
      port: svc.port,
      public: svc.public,
      core: svc.core,
      description: svc.description,
      // Use D1 value if set, otherwise use default from tfvars
      enabled: Object.hasOwn(enabledMap, svc.name) 
        ? enabledMap[svc.name] 
        : svc.defaultEnabled,
    }));

    return new Response(JSON.stringify({
      success: true,
      services,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services GET error:', error);
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

    // Save to D1 (no deployment - user clicks Spin Up when ready)
    await setServiceEnabled(env.NEXUS_DB, serviceName, enabled);

    // Log the service toggle
    await logApiCall(env.NEXUS_DB, '/api/services', 'POST', {
      action: 'toggle_service',
      service: serviceName,
      enabled: enabled,
    });

    // Get updated enabled map for response
    const enabledMap = await getEnabledServicesFromD1(env.NEXUS_DB);
    const enabledServices = serviceDefinitions
      .filter(svc => {
        if (Object.hasOwn(enabledMap, svc.name)) {
          return enabledMap[svc.name];
        }
        return svc.defaultEnabled;
      })
      .map(svc => svc.name);

    return new Response(JSON.stringify({
      success: true,
      message: `Service ${serviceName} ${enabled ? 'enabled' : 'disabled'}. Click "Spin Up" to deploy changes.`,
      enabledServices,
      pendingChanges: true,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services POST error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to update service',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
