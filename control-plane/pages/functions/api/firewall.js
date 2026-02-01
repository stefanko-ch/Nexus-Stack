/**
 * Manage firewall rules for external TCP access
 * GET /api/firewall - Get all firewall rules from D1
 * POST /api/firewall - Toggle a firewall rule or update source IPs
 *
 * Firewall rules control which TCP ports are opened on the Hetzner firewall
 * for direct external access (e.g., Kafka, PostgreSQL, MinIO S3 API).
 * Rules are staged in D1 and applied on the next Spin Up.
 * All rules are reset on Teardown for security.
 */

import { logApiCall, logError } from './_utils/logger.js';

/**
 * Validate service name to prevent injection attacks
 */
function validateServiceName(name) {
  if (typeof name !== 'string') return false;
  if (name.length === 0 || name.length > 63) return false;
  return /^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$/.test(name);
}

/**
 * Validate port number
 */
function validatePort(port) {
  return typeof port === 'number' && Number.isInteger(port) && port >= 1 && port <= 65535;
}

/**
 * Validate source IPs (comma-separated CIDRs)
 */
function validateSourceIps(sourceIps) {
  if (typeof sourceIps !== 'string') return false;
  if (sourceIps.trim() === '') return true; // empty = open to all

  const cidrs = sourceIps.split(',').map(s => s.trim());
  const ipv4CidrRegex = /^(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)){3})(?:\/(?:[0-9]|[12]\d|3[0-2]))?$/;
  const ipv6CidrRegex = /^([0-9a-fA-F:]+)(?:\/(?:12[0-8]|1[01]\d|[1-9]?\d))?$/;

  for (const cidr of cidrs) {
    if (!ipv4CidrRegex.test(cidr) && !ipv6CidrRegex.test(cidr)) return false;
  }
  return true;
}

/**
 * GET /api/firewall
 * Returns all firewall rules from D1
 */
export async function onRequestGet(context) {
  const { env } = context;

  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured',
      rules: [],
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const results = await env.NEXUS_DB.prepare(`
      SELECT service_name, port, protocol, label, enabled, deployed, source_ips, dns_record
      FROM firewall_rules
      ORDER BY service_name, port
    `).all();

    let pendingChangesCount = 0;
    const rules = (results.results || []).map(row => {
      const enabled = row.enabled === 1;
      const deployed = row.deployed === 1;
      const hasPendingChange = enabled !== deployed;

      if (hasPendingChange) {
        pendingChangesCount++;
      }

      return {
        serviceName: row.service_name,
        port: row.port,
        protocol: row.protocol,
        label: row.label || '',
        enabled,
        deployed,
        pending: hasPendingChange,
        sourceIps: row.source_ips || '',
        dnsRecord: row.dns_record || '',
      };
    });

    // Get domain from environment or config
    const domain = env.DOMAIN || '';

    return new Response(JSON.stringify({
      success: true,
      rules,
      pendingChangesCount,
      domain,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Firewall GET error:', error);
    await logError(env.NEXUS_DB, '/api/firewall', 'GET', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to load firewall rules',
      rules: [],
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

/**
 * POST /api/firewall
 * Toggle a firewall rule or update source IPs
 * Body: { service: string, port: number, enabled: boolean, sourceIps?: string }
 */
export async function onRequestPost(context) {
  const { env, request } = context;

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
    const body = await request.json();
    const serviceName = body.service;
    const port = body.port;
    const enabled = body.enabled;
    const sourceIps = body.sourceIps;

    // Validate required fields
    if (!serviceName || !validatePort(port) || typeof enabled !== 'boolean') {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid payload. Expected { service: string, port: number, enabled: boolean, sourceIps?: string }',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (!validateServiceName(serviceName)) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid service name format.',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Validate source IPs if provided
    if (sourceIps !== undefined && !validateSourceIps(sourceIps)) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid source IPs format. Use comma-separated CIDRs (e.g., "10.0.0.0/8,192.168.1.0/24").',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Check if the firewall rule exists
    const rule = await env.NEXUS_DB.prepare(
      'SELECT service_name, port, deployed FROM firewall_rules WHERE service_name = ? AND port = ?'
    ).bind(serviceName, port).first();

    if (!rule) {
      return new Response(JSON.stringify({
        success: false,
        error: `Firewall rule not found: ${serviceName}:${port}. Run firewall init first.`,
      }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Update the rule
    if (sourceIps !== undefined) {
      await env.NEXUS_DB.prepare(`
        UPDATE firewall_rules SET enabled = ?, source_ips = ?, updated_at = datetime('now')
        WHERE service_name = ? AND port = ?
      `).bind(enabled ? 1 : 0, sourceIps, serviceName, port).run();
    } else {
      await env.NEXUS_DB.prepare(`
        UPDATE firewall_rules SET enabled = ?, updated_at = datetime('now')
        WHERE service_name = ? AND port = ?
      `).bind(enabled ? 1 : 0, serviceName, port).run();
    }

    await logApiCall(env.NEXUS_DB, '/api/firewall', 'POST', {
      action: 'toggle_firewall_rule',
      service: serviceName,
      port,
      enabled,
      sourceIps: sourceIps || '',
    });

    // Get pending changes count
    const pendingResult = await env.NEXUS_DB.prepare(`
      SELECT COUNT(*) as count FROM firewall_rules WHERE enabled != deployed
    `).first();
    const pendingChangesCount = pendingResult?.count || 0;

    return new Response(JSON.stringify({
      success: true,
      message: `Firewall rule ${serviceName}:${port} ${enabled ? 'enabled' : 'disabled'}. Click "Spin Up" to apply changes.`,
      pendingChangesCount,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Firewall POST error:', error);
    await logError(env.NEXUS_DB, '/api/firewall', 'POST', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Failed to update firewall rule',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
