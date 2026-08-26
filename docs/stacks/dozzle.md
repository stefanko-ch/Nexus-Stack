---
title: "Dozzle"
---

## Dozzle

![Dozzle](https://img.shields.io/badge/Dozzle-7B16FF?logo=docker&logoColor=white)

**Realtime Docker logs in the browser**

Dozzle is a tiny web UI that streams `docker logs` for every running container live. No persistent state, no database — it subscribes to the Docker events stream via the read-only socket mount and follows container log files. Features:

- Live log tail for every container on the host, all in one sidebar
- Search + filter (substring, regex, plain text)
- Jump between containers; multi-tab parallel tailing
- Resource graphs per container (CPU, memory) on hover
- Stat-the-container view: image, env, mounts, network, ports
- Container list auto-updates as you spin services up/down

| Setting | Value |
|---------|-------|
| Default Port | `8480` |
| Suggested Subdomain | `dozzle` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [dozzle.dev](https://dozzle.dev) |
| Source | [GitHub](https://github.com/amir20/dozzle) |
| Docker image | [`amir20/dozzle`](https://hub.docker.com/r/amir20/dozzle) |

### Usage

1. Enable **Dozzle** in the Control Plane → Spin Up
2. Visit `https://dozzle.YOUR_DOMAIN`, authenticate via Cloudflare Access OTP
3. The left sidebar lists every container on the host; click one to tail its logs
4. Use the search bar (top right) to filter the active stream

### Operator workflows it replaces

- **"Why did metabase just restart?"** Old: `ssh nexus && docker logs metabase --tail 200`. New: open Dozzle, click `metabase`, scroll to the most recent stack trace.
- **"Is the spin-up workflow done?"** Old: `ssh nexus && docker ps -a` and scan for restart-loops. New: open Dozzle, scan the container sidebar — restarting containers are highlighted.
- **Multi-container debugging during a deploy:** open Dozzle in two browser tabs, one tailing `forgejo`, one tailing `kestra-postgres`, watch them come up in order during a spin-up.

### Auth model

Dozzle has its own basic-auth and OIDC modes, but we disable them (`DOZZLE_NO_AUTH=true`) and rely on **Cloudflare Access (email OTP)** at the edge — same model as Grafana and Infisical (Forgejo is the exception — it keeps its own login on top of Access), every other admin UI in Nexus-Stack. CF Access in front + no second-layer auth in the container avoids double-prompting and a redundant password to manage in Infisical.

### Security note

The container mounts `/var/run/docker.sock:/var/run/docker.sock:ro` — **read-only**. Dozzle only needs the `events` and `logs` Docker API endpoints, both of which work over a read-only socket. The `:ro` flag is defence-in-depth in case a future Dozzle release adds a feature that would `exec`/`kill` containers — they wouldn't be reachable through a read-only socket. Anyone who can authenticate via CF Access can see all container logs (including any tokens/passwords that services log accidentally) — same exposure as `ssh nexus + docker logs` for the operator.
