-- =============================================================================
-- Nexus-Stack Control Plane D1 Schema
-- =============================================================================
-- This schema stores control plane configuration.
-- Credentials are NOT stored here - they go in Cloudflare Secrets.
-- =============================================================================

-- Configuration key-value store
-- Used for: scheduled teardown settings, timezone, etc.
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Service enabled/disabled state
-- Stores which services are enabled in the Control Plane UI
-- enabled = what the user wants (staged)
-- deployed = what is currently running
-- Metadata (subdomain, port, etc.) is synced from services.yaml
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    deployed INTEGER NOT NULL DEFAULT 0,
    subdomain TEXT DEFAULT '',
    port INTEGER DEFAULT 0,
    public INTEGER DEFAULT 0,
    core INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Logs
-- Stores logs from various sources: GitHub Actions, Workers, API, health checks
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,            -- e.g., 'github-action', 'worker', 'api', 'health-check'
    run_id TEXT,                      -- Correlation ID (e.g., GitHub Actions run ID)
    level TEXT DEFAULT 'info',        -- 'debug', 'info', 'warn', 'error'
    message TEXT NOT NULL,
    metadata TEXT,                    -- JSON blob for additional context
    created_at TEXT DEFAULT (datetime('now'))
);

-- Index for efficient log queries
CREATE INDEX IF NOT EXISTS idx_logs_source ON logs(source);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);

-- Insert default configuration values
INSERT OR IGNORE INTO config (key, value) VALUES 
    ('teardown_enabled', 'true'),
    ('teardown_timezone', 'Europe/Zurich'),
    ('teardown_time', '22:00'),
    ('notification_time', '21:45'),
    ('server_type', 'cax31'),
    ('server_location', 'fsn1');
