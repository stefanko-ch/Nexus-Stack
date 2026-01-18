/**
 * D1 Logger Utility
 * 
 * Provides consistent logging across all API endpoints.
 * Logs are stored in the D1 logs table.
 */

/**
 * Insert a log entry into D1
 * @param {D1Database} db - D1 database binding
 * @param {string} source - Log source (e.g., 'api', 'worker', 'github-action')
 * @param {string} level - Log level ('debug', 'info', 'warn', 'error')
 * @param {string} message - Log message
 * @param {object} metadata - Additional context (optional)
 */
export async function log(db, source, level, message, metadata = null) {
  if (!db) return;
  
  try {
    const metadataJson = metadata ? JSON.stringify(metadata) : null;
    await db.prepare(
      'INSERT INTO logs (source, level, message, metadata) VALUES (?, ?, ?, ?)'
    ).bind(source, level, message, metadataJson).run();
  } catch (error) {
    // Don't let logging errors break the API
    console.error('Failed to log to D1:', error);
  }
}

/**
 * Log an API call with request details
 * @param {D1Database} db - D1 database binding
 * @param {string} endpoint - API endpoint name
 * @param {string} method - HTTP method
 * @param {object} details - Additional details (user action, result, etc.)
 */
export async function logApiCall(db, endpoint, method, details = {}) {
  await log(db, 'api', 'info', `${method} ${endpoint}`, {
    endpoint,
    method,
    ...details,
    timestamp: new Date().toISOString(),
  });
}

/**
 * Log an error with stack trace
 * @param {D1Database} db - D1 database binding
 * @param {string} source - Log source
 * @param {string} message - Error message
 * @param {Error} error - Error object
 */
export async function logError(db, source, message, error) {
  await log(db, source, 'error', message, {
    error: error.message,
    stack: error.stack?.substring(0, 500),
    timestamp: new Date().toISOString(),
  });
}
