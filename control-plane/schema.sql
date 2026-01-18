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
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Insert default configuration values
INSERT OR IGNORE INTO config (key, value) VALUES 
    ('teardown_enabled', 'true'),
    ('teardown_timezone', 'Europe/Zurich'),
    ('teardown_time', '22:00'),
    ('notification_time', '21:45');
