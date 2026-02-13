## Prefect

![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)

**Modern Python-native workflow orchestration for data pipelines and automation.**

| Detail | Value |
|--------|-------|
| Port | `4200` |
| Subdomain | `prefect.<domain>` |
| Source | [GitHub](https://github.com/PrefectHQ/prefect) |

### Architecture

Prefect runs as 4 containers:

| Container | Purpose |
|-----------|---------|
| `prefect` | API server + web UI |
| `prefect-services` | Background services (scheduler, triggers, events) |
| `prefect-worker` | Local flow executor (work pool: `local-pool`) |
| `prefect-db` | Dedicated PostgreSQL database |

### Usage

1. Enable the Prefect service in the Control Plane
2. Access `https://prefect.<domain>` to open the Prefect UI
3. Create flows using Python and deploy them via the API
4. The local worker automatically picks up flow runs from the `local-pool` work pool

### Connecting from Other Services

Services running on the same Docker network can connect to Prefect using:

```
PREFECT_API_URL=http://prefect:4200/api
```

> No authentication required - Cloudflare Access provides email OTP protection at the network level.
