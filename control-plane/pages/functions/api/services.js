/**
 * Manage services configuration
 * GET /api/services
 * POST /api/services
 */

function decodeBase64(input) {
  if (typeof atob === 'function') {
    return atob(input);
  }
  return Buffer.from(input, 'base64').toString('utf-8');
}

function encodeBase64(input) {
  if (typeof btoa === 'function') {
    return btoa(input);
  }
  return Buffer.from(input, 'utf-8').toString('base64');
}

function parseServicesConfig(content) {
  const services = [];
  const lines = content.split('\n');
  let current = null;
  let inBlock = false;

  for (const line of lines) {
    const serviceMatch = line.match(/^\s*([a-zA-Z0-9-]+)\s*=\s*\{\s*$/);
    if (serviceMatch) {
      current = { name: serviceMatch[1], enabled: null, description: '' };
      inBlock = true;
      continue;
    }

    if (inBlock && current) {
      const enabledMatch = line.match(/^\s*enabled\s*=\s*(true|false)\s*$/);
      if (enabledMatch) {
        current.enabled = enabledMatch[1] === 'true';
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

function updateServiceEnabled(content, serviceName, enabled) {
  const lines = content.split('\n');
  let inBlock = false;
  let foundService = false;
  let updated = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const serviceMatch = line.match(/^\s*([a-zA-Z0-9-]+)\s*=\s*\{\s*$/);
    if (serviceMatch) {
      inBlock = serviceMatch[1] === serviceName;
      foundService = foundService || inBlock;
      continue;
    }

    if (inBlock) {
      const enabledMatch = line.match(/^\s*enabled\s*=\s*(true|false)\s*$/);
      if (enabledMatch) {
        lines[i] = line.replace(enabledMatch[1], enabled ? 'true' : 'false');
        updated = true;
        inBlock = false;
      }

      if (line.trim() === '}') {
        inBlock = false;
      }
    }
  }

  if (!foundService) {
    throw new Error(`Service not found: ${serviceName}`);
  }

  if (!updated) {
    throw new Error(`Failed to update service: ${serviceName}`);
  }

  return lines.join('\n');
}

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

async function updateServicesFile(env, content, sha, message) {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/contents/tofu/services.tfvars`;
  const payload = {
    message,
    content: encodeBase64(content),
    sha,
    branch: 'main',
  };

  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'Nexus-Stack-Control-Plane',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to update file (${response.status}): ${errorText.substring(0, 200)}`);
  }

  return response.json();
}

async function triggerSpinUp(env) {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/spin-up.yml/dispatches`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'Nexus-Stack-Control-Plane',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ref: 'main', inputs: { send_credentials: 'false' } }),
  });

  if (response.status !== 204) {
    const errorText = await response.text();
    throw new Error(`Failed to trigger spin-up (${response.status}): ${errorText.substring(0, 200)}`);
  }
}

export async function onRequestGet(context) {
  const { env } = context;

  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return new Response(JSON.stringify({
      success: false,
      error: 'Missing required environment variables',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const file = await fetchServicesFile(env);
    const content = decodeBase64(file.content || '');
    const services = parseServicesConfig(content);

    return new Response(JSON.stringify({
      success: true,
      services,
      sha: file.sha,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services GET error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Failed to load services',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

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

  try {
    const body = await request.json();
    const service = body.service;
    const enabled = body.enabled;

    if (!service || typeof enabled !== 'boolean') {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid payload. Expected { service, enabled }',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const file = await fetchServicesFile(env);
    const content = decodeBase64(file.content || '');
    const updatedContent = updateServiceEnabled(content, service, enabled);

    await updateServicesFile(
      env,
      updatedContent,
      file.sha,
      `chore: ${enabled ? 'enable' : 'disable'} ${service}`
    );

    await triggerSpinUp(env);

    return new Response(JSON.stringify({
      success: true,
      message: `Service ${service} updated and spin-up triggered`,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Services POST error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Failed to update service',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
