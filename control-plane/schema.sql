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
    admin_only INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    category TEXT DEFAULT '',
    website TEXT DEFAULT '',
    long_description TEXT DEFAULT '',
    landing_path TEXT DEFAULT '',
    api_only INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_services_category ON services(category);
CREATE INDEX IF NOT EXISTS idx_services_enabled ON services(enabled);

-- Firewall rules for external TCP access
-- Controls which ports are opened on the Hetzner firewall for direct TCP connections
-- enabled = what the user wants (staged)
-- deployed = what is currently running
-- Rules are reset (enabled = 0) on every Teardown for security
CREATE TABLE IF NOT EXISTS firewall_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL DEFAULT 'tcp',
    label TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 0,
    deployed INTEGER NOT NULL DEFAULT 0,
    -- New rows default to explicit allow-all (operators MUST narrow this
    -- in the Control Plane UI). Empty source_ips no longer carries a
    -- silent allow-all semantics — the OpenTofu module hard-fails on
    -- empty firewall_rules.source_ips and generate-services-tfvars.py
    -- translates legacy empty rows to this same explicit allow-all
    -- with a deprecation warning. CREATE TABLE IF NOT EXISTS means
    -- the new DEFAULT only applies to fresh installs; existing rows
    -- with the old '' default are handled by the script's migration
    -- shim until operators set their own source_ips.
    source_ips TEXT DEFAULT '0.0.0.0/0,::/0',
    dns_record TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(service_name, port)
);

CREATE INDEX IF NOT EXISTS idx_firewall_rules_service ON firewall_rules(service_name);
CREATE INDEX IF NOT EXISTS idx_firewall_rules_enabled ON firewall_rules(enabled);

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
    ('server_type', 'cx43'),
    ('server_location', 'hel1'),
    ('notify_on_shutdown', 'true'),
    ('notify_on_spinup', 'true'),
    ('silent_mode', 'false'),
    -- Which lifecycle workflow pair to dispatch: 'rebuild' (destroy and
    -- rebuild from ubuntu-24.04) or 'snapshot' (snapshot the disk,
    -- destroy only the server, restore from the image).
    --
    -- ONE key, not one per workflow. Two independent keys could drift,
    -- and a half-applied switch is harmful rather than merely untidy:
    -- snapshot spin-up with rebuild teardown means the nightly untargeted
    -- `tofu destroy` rotates every generated credential and orphans the
    -- snapshot it just produced.
    ('lifecycle_mode', 'rebuild');

-- ---------------------------------------------------------------------------
-- Migration: 'legacy' -> 'rebuild'
--
-- 'legacy' was the original name for this pair and described it wrongly:
-- it is not deprecated. It is the permanent fallback whenever a snapshot
-- is unusable, the only option across an architecture change, and
-- spin-up.yml is the shared engine the snapshot spin-up itself calls via
-- workflow_call. The name is now 'rebuild', which says what it does.
--
-- No alias is kept in code, deliberately: an alias keeps a name alive
-- that nobody should use. This file is applied on every
-- setup-control-plane run, so every stack is migrated the next time its
-- Control Plane is deployed.
--
-- ORDERING, and the one rough edge: the Worker is deployed before this
-- runs, so the scheduled teardown never sees a value it cannot read. The
-- Pages Functions are deployed AFTER, so between this statement and that
-- step the API is briefly serving code that does not know 'rebuild' and
-- will answer 503. That window is minutes long, only during a deliberate
-- deploy, and it fails closed rather than dispatching the wrong pair.
--
-- Idempotent: after the first run no row matches.
UPDATE config
   SET value = 'rebuild', updated_at = datetime('now')
 WHERE key = 'lifecycle_mode' AND value = 'legacy';
