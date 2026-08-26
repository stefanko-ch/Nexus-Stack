---
title: "Portainer"
---

## Portainer

![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)

**Always-on Docker dashboard — first stop for diagnosing a misbehaving container**

Portainer is a **core service** in Nexus-Stack: it's auto-deployed alongside Forgejo, Grafana, and Infisical, and the Control Plane Stacks page does not let you disable it. The reason: when something goes wrong on a deployed stack — container in restart-loop, OOM-killed, image pull failure, port collision — Portainer is the operator's first stop. Requiring an opt-in step before you can see *why* a container won't start would be the wrong design.

What you get out of the box:
- Container view (state, restart, logs, exec into a shell, resource usage)
- Image inspection (layers, env, entrypoint)
- Volume + network management
- Stack deployment with Docker Compose (rarely needed in this project — `scripts/deploy.sh` handles stack lifecycle — but useful for ad-hoc experiments)

| Setting | Value |
|---------|-------|
| Default Port | `9090` (→ internal 9000) |
| Suggested Subdomain | `portainer` |
| Public Access | **Never** (always protected, Cloudflare Access OTP on top) |
| Always Enabled | ✓ — `core: true` in `services.yaml`. Cannot be disabled in the Control Plane Stacks page. |
| Website | [portainer.io](https://www.portainer.io) |
| Source | [GitHub](https://github.com/portainer/portainer) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Credentials are available in Infisical.
