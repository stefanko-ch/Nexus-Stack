---
title: "Centralised Monitoring Integration"
---

# Centralised Monitoring Integration

Optional opt-in feature that lets a Nexus-Stack instance push its
existing Prometheus metrics to a central monitoring tier
(VictoriaMetrics + Grafana) for cross-stack visibility.

**Default behaviour:** off. When the two secrets are unset (every
existing stack), Prometheus runs exactly as before — metrics stay
local, the per-stack Grafana keeps working unchanged. There is no
behaviour change unless you set the secrets.

## Architecture

```
Your Nexus-Stack (Hetzner VM)
  prometheus + node_exporter + cAdvisor + promtail
                │
                └── remote_write → MONITORING_ENDPOINT/api/v1/write
                    (Bearer MONITORING_TOKEN, per-tenant)
                                │
                                ▼
Central Monitoring Tier (e.g. Nexus-Conductor's CAX21)
  vmauth → victoria-metrics → grafana
  (operator dashboards across all enrolled stacks)
```

The receiving end is provided by [Nexus-Conductor](https://github.com/stefanko-ch/Nexus-Conductor)
— a separate project that issues per-tenant tokens, runs vmauth in
front of VictoriaMetrics, and serves operator dashboards. You can also
point at any other Prometheus-`remote_write`-compatible endpoint
(Grafana Cloud, your own VictoriaMetrics, etc.).

## Enabling

Three GitHub Actions repository secrets, all optional. Set the first
two together to enable; leaving either empty keeps remote_write off.

| Secret | Required | Value |
|---|---|---|
| `MONITORING_ENDPOINT` | Yes (with TOKEN) | `https://metrics.<your-monitoring-host>` (no trailing `/api/v1/write` — the renderer appends it) |
| `MONITORING_TOKEN` | Yes (with ENDPOINT) | Bearer token issued by your central monitoring tier (per-stack / per-tenant) |
| `TENANT_ID` | Optional | Tenant label injected into every series. Defaults to your `DOMAIN` secret when unset |

Set them under **Settings → Secrets and variables → Actions → New
repository secret**, then run **Spin Up** — the next render of
`stacks/grafana/prometheus.yml` will include the `remote_write` block.

## Disabling

Remove the `MONITORING_ENDPOINT` (or `MONITORING_TOKEN`) secret from
the repo. The next Spin Up regenerates `prometheus.yml` with a
single-line `# remote_write disabled` comment in place of the
`remote_write` block. No restart-loop, no error — Prometheus is happy
with no `remote_write` at all.

## What gets sent

Every Prometheus scrape target you already run locally:

- `prometheus` (Prometheus self-monitoring)
- `node-exporter` (host CPU/RAM/Disk/Network)
- `cadvisor` (per-container CPU/RAM/network)
- `risingwave` (if enabled)

Two relabel rules filter the stream:

1. **Cardinality drop**: series matching `(go_|process_|promhttp_).*`
   are dropped at the stack's `remote_write` boundary. These are
   Prometheus-runtime internals (Go GC stats, HTTP handler counters)
   that are useless for cross-stack monitoring and would inflate the
   central VM's series budget. Saves ~30% of the egress + central-side
   cost per stack.
2. **Tenant label**: every series gets `tenant=<TENANT_ID>` (or
   `tenant=<DOMAIN>` as fallback). This is informational — the central
   `vmauth` proxy enforces the real tenant binding server-side from
   the token → tenant_id mapping, so a malicious stack can't spoof
   another tenant's bucket by editing this label.

## Resource impact

- **RAM**: ~1-2 MB extra for the `remote_write` WAL buffer
- **CPU**: negligible (~1-2% of one core during normal scraping)
- **Network egress**: ~1-2 KB/s per stack ≈ 5-10 GB/month
  - Well within Hetzner's free 20 TB/month egress
- **Disk**: no impact (local TSDB unchanged, 15d retention)

## Backpressure & failure modes

If the central monitoring tier is unreachable:

- Prometheus's local WAL buffers up to ~5h of samples (default)
- After 5h, the oldest unsent samples drop silently — bounded loss,
  not unbounded growth
- When the central side recovers, each stack flushes its buffer in
  one burst (~10× normal load for 5-10 min) — the receiver should be
  sized to absorb this; see [Nexus-Conductor #23](https://github.com/stefanko-ch/Nexus-Conductor/issues/23)
  for sizing guidance

If the central side returns `HTTP 429 Too Many Requests` (rate limit
hit), Prometheus's `remote_write` respects it and backs off
exponentially — no manual intervention needed.

## Security

- **Token storage**: the Bearer token is baked into
  `stacks/grafana/prometheus.yml` at render time. The file is
  generated with mode `0o644` — the bind-mounted config has to be
  readable by the non-root Prometheus container process (UID 65534
  in `prom/prometheus:2.x+`); a stricter mode would lock Prometheus
  out of its own config. Token confidentiality rests on the
  host-access barrier instead: SSH is locked to the Cloudflare
  Tunnel + email OTP, and the token also lives in Infisical +
  GitHub Actions secrets — the rendered file isn't its only home.
- **Token rotation**: rotate the central-side token, update
  `MONITORING_TOKEN` in your repo secrets, run Spin Up. Old token
  stops working once vmauth picks up the revocation (typically
  within 60s of the central-side change).
- **Cross-tenant isolation**: enforced at the central `vmauth`
  proxy. The stack-side relabel that adds the tenant label is
  informational; vmauth will reject writes whose token doesn't
  authorize the claimed tenant label.

## Files involved

- `stacks/grafana/prometheus.yml.template` — human-editable template
  (committed)
- `stacks/grafana/prometheus.yml` — generated at render time
  (gitignored, mode 0o644 — container-readable; see Security above)
- `stacks/grafana/.gitignore` — excludes the generated file
- `src/nexus_deploy/service_env.py` — `_render_grafana` +
  `_render_prometheus_remote_write_block` helpers
- `src/nexus_deploy/infisical.py` — `BootstrapEnv` fields
  `monitoring_endpoint` / `monitoring_token` / `tenant_id`
- `.github/workflows/spin-up.yml` — secret passthroughs to
  `python -m nexus_deploy run-pipeline`

## Manual smoke test

To verify locally before enrolling with a real central tier, run a
mock receiver that returns `200 OK` to POSTs (Prometheus'
`remote_write` is POST-only — Python's stock `http.server` returns
`501 Not Implemented` for POST and won't work here):

```bash
# Terminal 1 — mock receiver that accepts POST and logs the request.
# Authorization header is REDACTED (we only log presence + token length)
# so a real production token doesn't end up in the terminal scrollback
# if you re-use this recipe with non-test credentials.
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        auth = self.headers.get('Authorization', '')
        auth_summary = f'present (Bearer prefix, {len(auth) - 7} char token)' if auth.startswith('Bearer ') else ('missing' if not auth else 'present (no Bearer prefix)')
        print(f'{self.command} {self.path} auth={auth_summary} bytes={len(body)}')
        self.send_response(200); self.end_headers()
HTTPServer(('0.0.0.0', 9999), Handler).serve_forever()
"

# Terminal 2 — temporary repo secrets.
# MONITORING_ENDPOINT is a URL (not sensitive) so --body inline is fine.
# MONITORING_TOKEN IS sensitive — use stdin so the value never appears in
# shell history or `ps` listings. The same advice applies for the real
# token from your production central-monitoring tier — never paste it
# into `--body "..."`.
gh secret set MONITORING_ENDPOINT --body "http://<your-runner-tunnel>:9999"
printf 'test-token-123' | gh secret set MONITORING_TOKEN
# Or use the GitHub UI: Settings → Secrets and variables → Actions → New
# repository secret (the value is typed into a password field, no shell at all).

# Trigger spin-up, then SSH to the server and tail logs:
ssh nexus "docker logs grafana-prometheus 2>&1 | grep -i remote"
```

You should see `remote_write` POSTs with the correct Bearer header
within ~15s of Prometheus starting.

## Related

- [Issue #607](https://github.com/stefanko-ch/Nexus-Stack/issues/607) — feature spec
- [Nexus-Conductor #23](https://github.com/stefanko-ch/Nexus-Conductor/issues/23) — central-side architecture
- [stacks/grafana documentation](../stacks/grafana.md)
