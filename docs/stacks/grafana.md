---
title: "Grafana"
---

## Grafana

![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)

**Full observability stack with Prometheus, Loki & dashboards**

A complete monitoring and observability solution including:
- **Grafana** - Beautiful dashboards and visualization
- **Prometheus** - Metrics collection and alerting
- **Loki** - Log aggregation (like Prometheus, but for logs)
- **Promtail** - Ships Docker container logs to Loki
- **cAdvisor** - Container metrics (CPU, memory, network, disk)
- **Node Exporter** - Host-level metrics (CPU, RAM, disk, network)

| Setting | Value |
|---------|-------|
| Default Port | `3100` (→ internal 3000) |
| Suggested Subdomain | `grafana` |
| Public Access | **Never** (always protected) |
| Website | [grafana.com](https://grafana.com) |
| Source | [GitHub](https://github.com/grafana/grafana) |

### Pre-configured Dashboards

The stack comes with three ready-to-use dashboards:

| Dashboard | Description |
|-----------|-------------|
| **Docker Overview** | Container CPU, memory, network I/O, and disk usage |
| **Loki Logs** | Real-time log viewing and filtering for all containers |
| **Node Exporter** | Host metrics including CPU, memory, disk, and network |

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Containers │────▶│  Promtail   │────▶│    Loki     │
│   (logs)    │     │             │     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
┌─────────────┐     ┌─────────────┐            │
│  cAdvisor   │────▶│ Prometheus  │            │
│  (metrics)  │     │             │────────────┼──────▶ Grafana
└─────────────┘     └──────┬──────┘            │
                           │                   │
┌─────────────┐            │                   │
│Node Exporter│────────────┘                   │
│(host stats) │                                │
└─────────────┘                                │
```

> ✅ **Auto-configured:** Admin password is set via environment variables during deployment. Dashboards and datasources are pre-provisioned. Credentials are available in Infisical.

### cAdvisor runs unprivileged

cAdvisor collects the per-container CPU, memory and network metrics behind
the Docker overview dashboard. It runs **without** `privileged: true`, which
is worth knowing because most examples on the internet include that flag.

cAdvisor's own documentation names two situations that require it, and
neither applies here:

- **Process metrics** (`--enable_metrics=process`), which additionally need
  `--pid=host`. Not enabled. Every metric the shipped dashboards query —
  `container_cpu_usage_seconds_total`, `container_memory_usage_bytes`,
  `container_last_seen`, `container_network_receive_bytes_total`,
  `container_network_transmit_bytes_total` — is read from the cgroup
  hierarchy under the read-only `/sys` mount.
- **RHEL and CentOS**, which confine containers more tightly. The servers
  run Ubuntu 26.04.

`/dev/kmsg` is passed through explicitly as a device, and read-only:
`- /dev/kmsg:/dev/kmsg:r`. cAdvisor reads it to detect OOM kills, and that
is the one thing the privileged flag was providing without saying so. The
`:r` matters — Docker defaults a device entry to `rwm`, which would grant
write access to the host kernel log and give back part of what dropping
`privileged` removed.

The reason to care: a privileged container holds every Linux capability, an
unconfined seccomp profile and access to host devices. This stack also
mounts the Docker socket, so a compromise of the monitoring stack would be
a compromise of the host — and monitoring is by design the one stack wired
to reach all the others.

**If a panel goes blank after a deploy**, check in this order:

```bash
# 1. Is cAdvisor exporting at all?
ssh nexus "docker exec grafana-cadvisor wget -qO- http://localhost:8080/healthz"

# 2. Does the specific metric exist?
ssh nexus "docker exec grafana-cadvisor wget -qO- http://localhost:8080/metrics | grep -c container_cpu_usage_seconds_total"

# 3. Anything permission-shaped in the log?
ssh nexus "docker logs grafana-cadvisor 2>&1 | grep -iE 'permission|denied|failed to'"
```

A metric missing at step 2 with a permission error at step 3 would mean this
host needs more than the current configuration grants. That has not been
observed on Ubuntu; if it happens, record which metric and which error here
rather than restoring the flag silently.
