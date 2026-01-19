/**
 * Logs API
 * GET /api/logs - Get logs (with optional filters)
 * POST /api/logs - Write a log entry
 * DELETE /api/logs - Clear old logs
 * 
 * Used by GitHub Actions, Workers, and other components to store logs in D1.
 */

// D1 Helper Functions
async function insertLog(db, source, runId, level, message, metadata) {
  const metadataJson = metadata ? JSON.stringify(metadata) : null;
  await db.prepare(
    'INSERT INTO logs (source, run_id, level, message, metadata) VALUES (?, ?, ?, ?, ?)'
  ).bind(source, runId, level, message, metadataJson).run();
}

async function getLogs(db, options = {}) {
  const { source, level, limit = 100, offset = 0 } = options;
  
  let query = 'SELECT * FROM logs WHERE 1=1';
  const params = [];
  
  if (source) {
    query += ' AND source = ?';
    params.push(source);
  }
  if (level) {
    query += ' AND level = ?';
    params.push(level);
  }
  
  query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?';
  params.push(limit, offset);
  
  const stmt = db.prepare(query);
  const results = await stmt.bind(...params).all();
  
  return results.results || [];
}

async function deleteOldLogs(db, daysToKeep = 30) {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - daysToKeep);
  const cutoffStr = cutoff.toISOString().replace('T', ' ').substring(0, 19);
  
  const result = await db.prepare(
    'DELETE FROM logs WHERE created_at < ?'
  ).bind(cutoffStr).run();
  
  return result.meta?.changes || 0;
}

/**
 * GET /api/logs
 * Query parameters:
 * - source: Filter by source (e.g., 'github-action', 'worker', 'api')
 * - level: Filter by log level
 * - limit: Max results (default 100)
 * - offset: Pagination offset
 */
export async function onRequestGet(context) {
  const { env, request } = context;
  
  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const url = new URL(request.url);
    const source = url.searchParams.get('source');
    const level = url.searchParams.get('level');
    const limit = parseInt(url.searchParams.get('limit') || '100', 10);
    const offset = parseInt(url.searchParams.get('offset') || '0', 10);
    
    const logs = await getLogs(env.NEXUS_DB, { source, level, limit, offset });
    
    // Parse metadata JSON for each log
    const parsedLogs = logs.map(log => ({
      ...log,
      metadata: log.metadata ? JSON.parse(log.metadata) : null
    }));
    
    return new Response(JSON.stringify({
      success: true,
      logs: parsedLogs,
      count: parsedLogs.length,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Logs GET error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

/**
 * POST /api/logs
 * Body:
 * - source: (required) Log source (e.g., 'github-action', 'worker', 'api')
 * - run_id: Correlation ID (e.g., GitHub Actions run ID)
 * - level: 'debug' | 'info' | 'warn' | 'error' (default: 'info')
 * - message: (required) Log message
 * - metadata: Optional JSON object with additional context
 * 
 * Or batch mode:
 * - logs: Array of log entries
 */
export async function onRequestPost(context) {
  const { env, request } = context;
  
  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const body = await request.json();
    
    // Support batch mode
    const entries = body.logs || [body];
    let insertedCount = 0;
    
    for (const entry of entries) {
      const { source, run_id, level = 'info', message, metadata } = entry;
      
      if (!source || !message) {
        continue; // Skip invalid entries in batch mode
      }
      
      // Validate level
      const validLevels = ['debug', 'info', 'warn', 'error'];
      const normalizedLevel = validLevels.includes(level) ? level : 'info';
      
      await insertLog(env.NEXUS_DB, source, run_id, normalizedLevel, message, metadata);
      insertedCount++;
    }
    
    if (insertedCount === 0) {
      return new Response(JSON.stringify({
        success: false,
        error: 'No valid log entries provided. Required: source, message',
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    
    return new Response(JSON.stringify({
      success: true,
      message: `${insertedCount} log(s) written`,
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Logs POST error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

/**
 * DELETE /api/logs
 * Query parameters:
 * - days: Days to keep (default 30, deletes older logs)
 */
export async function onRequestDelete(context) {
  const { env, request } = context;
  
  if (!env.NEXUS_DB) {
    return new Response(JSON.stringify({
      success: false,
      error: 'D1 database not configured'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const url = new URL(request.url);
    const daysToKeep = parseInt(url.searchParams.get('days') || '30', 10);
    
    const deletedCount = await deleteOldLogs(env.NEXUS_DB, daysToKeep);
    
    return new Response(JSON.stringify({
      success: true,
      message: `Deleted ${deletedCount} log(s) older than ${daysToKeep} days`,
      deleted: deletedCount,
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Logs DELETE error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
