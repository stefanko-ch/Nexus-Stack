/**
 * Initialize services in D1 from services.tfvars
 * POST /api/services/init
 * 
 * Called by spin-up workflow after deployment to sync services.tfvars to D1.
 * This makes D1 the single source of truth for service state.
 * 
 * Behavior:
 * - For new services: creates entry with enabled=default, deployed=default
 * - For existing services: preserves enabled state, updates metadata
 * - Removes services that are no longer in tfvars
 */

import { logApiCall, logError } from '../_utils/logger.js';

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
      const enabledMatch = line.match(/^\s*enabled\s*=\s*(true|false)\s*$/);
      if (enabledMatch) {
        current.defaultEnabled = enabledMatch[1] === 'true';
      }

      const coreMatch = line.match(/^\s*core\s*=\s*(true|false)\s*$/);
      if (coreMatch) {
        current.core = coreMatch[1] === 'true';
      }

      const subdomainMatch = line.match(/^\s*subdomain\s*=\s*"(.*)"\s*$/);
      if (subdomainMatch) {
        current.subdomain = subdomainMatch[1];
      }

      const portMatch = line.match(/^\s*port\s*=\s*(\d+)\s*$/);
      if (portMatch) {
        current.port = parseInt(portMatch[1], 10);
      }

      const publicMatch = line.match(/^\s*public\s*=\s*(true|false)\s*$/);
      if (publicMatch) {
        current.public = publicMatch[1] === 'true';
      }

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

export async function onRequestPost(context) {
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

  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    // Fetch and parse services.tfvars from GitHub
    const file = await fetchServicesFile(env);
    const content = decodeBase64(file.content || '');
    const serviceDefinitions = parseServicesConfig(content);

    // Get existing services from D1
    const existingResults = await env.NEXUS_DB.prepare('SELECT name, enabled FROM services').all();
    const existingMap = {};
    for (const row of existingResults.results || []) {
      existingMap[row.name] = row.enabled === 1;
    }

    // Upsert all services from tfvars
    let created = 0;
    let updated = 0;

    for (const svc of serviceDefinitions) {
      const exists = Object.hasOwn(existingMap, svc.name);
      
      if (exists) {
        // Update metadata but preserve enabled state
        await env.NEXUS_DB.prepare(`
          UPDATE services SET
            subdomain = ?,
            port = ?,
            public = ?,
            core = ?,
            description = ?,
            updated_at = datetime('now')
          WHERE name = ?
        `).bind(
          svc.subdomain,
          svc.port,
          svc.public ? 1 : 0,
          svc.core ? 1 : 0,
          svc.description,
          svc.name
        ).run();
        updated++;
      } else {
        // Create new service with default enabled state
        await env.NEXUS_DB.prepare(`
          INSERT INTO services (name, enabled, deployed, subdomain, port, public, core, description, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        `).bind(
          svc.name,
          svc.defaultEnabled ? 1 : 0,
          svc.defaultEnabled ? 1 : 0,  // Initially deployed = enabled
          svc.subdomain,
          svc.port,
          svc.public ? 1 : 0,
          svc.core ? 1 : 0,
          svc.description
        ).run();
        created++;
      }
    }

    // Remove services that are no longer in tfvars
    const tfvarsNames = new Set(serviceDefinitions.map(s => s.name));
    let removed = 0;
    for (const name of Object.keys(existingMap)) {
      if (!tfvarsNames.has(name)) {
        await env.NEXUS_DB.prepare('DELETE FROM services WHERE name = ?').bind(name).run();
        removed++;
      }
    }

    await logApiCall(env.NEXUS_DB, '/api/services/init', 'POST', {
      action: 'init_services',
      created,
      updated,
      removed,
      total: serviceDefinitions.length,
    });

    return new Response(JSON.stringify({
      success: true,
      message: `Services initialized: ${created} created, ${updated} updated, ${removed} removed`,
      services: serviceDefinitions.length,
      created,
      updated,
      removed,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services init error:', error);
    await logError(env.NEXUS_DB, '/api/services/init', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to initialize services',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
