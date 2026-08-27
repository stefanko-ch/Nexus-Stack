---
title: "Debugging"
description: "How to debug issues with Nexus-Stack services"
order: 3
---

# Debugging Guide

This guide explains how to debug issues with Nexus-Stack services.

---

## Access Methods

### Option 1: SSH Access

For full server access via terminal. See the **[SSH Access Guide](ssh-access.md)** for setup instructions.

```bash
ssh nexus
```

### Option 2: Wetty (Web Terminal)

If Wetty is enabled, access it via browser at `https://wetty.yourdomain.com`. This provides a web-based terminal without SSH setup.

---

## Start Here: The Spin-Up Smoke Check

Before debugging by hand, read the **Check services answer** step at the end
of the last Spin Up run. It looks at every container on the server — running
or not — and tells you which one is the problem, often before you notice
anything is wrong.

It probes every published host port with HTTP — all of them, not just the
first, since a stack like RisingWave puts its Postgres wire protocol on one
port and its dashboard on another. It does not assume any of them speaks
HTTP, though: a port nothing is listening on and a healthy database that
simply is not a web server look identical in an HTTP status code. So the
check measures whether the TCP connection was established at all, which
keeps a non-HTTP listener out of the fault column. What does count as a
fault is listed in the table below.

```
  ok    forgejo                    :3202   200
  ok    portainer                  :9090   401
  --    postgres                   :5432   listening, not an HTTP service
  --    kestra-postgres                    no published port (internal-only)
  --    lakekeeper-bootstrap               ran once and exited cleanly
  FAIL  metabase                   :3000   nothing listening
  FAIL  superset                   :8088   503
  FAIL  openmetadata                       EXITED:1
  FAIL  woodpecker-agent                   restart loop

[smoke] 42 answering HTTP, 4 faulty, 13 with no HTTP endpoint to check
```

How to read it:

| Line | Meaning |
|---|---|
| `ok` with any 2xx/3xx/4xx | The application answered. `401` / `403` is a healthy service asking for a login, not a fault. |
| `--` / `no published port` | Internal-only container (databases, sidecars). Nothing to probe — not an error. |
| `--` / `ran once and exited cleanly` | A one-shot job that finished, such as `lakekeeper-bootstrap` or `openmetadata-migrate`. Expected. |
| `--` / `listening, not an HTTP service` | The port accepted the connection but answered something other than HTTP. Databases, brokers and SFTP land here — Postgres on 5432, Redpanda on 9092, ClickHouse on 9004. Healthy by every measure this check can take. |
| `FAIL` / `nothing listening` | No TCP connection was established at all. The container runs but the process inside never started listening. |
| `FAIL` / `accepted, then silent` | The port accepted the connection and then sent nothing for four seconds. Something is listening but not responding — distinct from a database that simply is not a web server, which answers or closes immediately. |
| `FAIL` with `5xx` | The service answered, so it is up and erroring — usually a bad config or an unreachable dependency. A different problem from silence. |
| `FAIL` with `EXITED:<n>` | The container stopped with a non-zero status. It crashed rather than started. |
| `FAIL` with `restart loop` | The container starts, fails, and Docker restarts it, over and over. Its logs hold the crash reason. |
| `FAIL` with `STATE:<x>` | The container is in a Docker state that is neither running nor cleanly exited — `created`, `paused` or `dead`. No port was probed. |
| `FAIL` with anything else | A result the check did not anticipate. That is a gap in the check rather than a diagnosis of the service; worth reporting as a bug. |

A `FAIL` never fails the workflow. The step runs *after* the deploy, so it
reports "the deploy finished and this one service is silent" — the server
itself is up. Failures appear as run annotations at the top of the run
summary, so you see them without opening the log.

Each `FAIL` names the container, which is exactly what
[Step 2](#step-2-check-container-logs) needs:

```bash
ssh nexus "docker logs metabase --tail 100"
```

**Skipping it:** the check is on by default. When dispatching Spin Up, clear
the *"Check every container after the deploy"* checkbox if you are iterating
on something unrelated and want the shortest cycle. It costs about ten
seconds, and that stays true when things are broken: the probes run on the
server in parallel, so twenty dead services cost one 4-second timeout, not
twenty.

---

## Systematic Debugging Process

When a service is not working, follow this systematic approach:

### Step 1: Check Container Status

```bash
# View all containers
docker ps -a

# Filter by service name
docker ps -a --filter "name=servicename"

# Check specific status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Status meanings:**
- `Up X minutes (healthy)` - Container running and health check passing
- `Up X minutes (unhealthy)` - Container running but health check failing
- `Up X minutes` (no health status) - Running, no health check configured
- `Exited (0)` - Container stopped normally
- `Exited (1)` - Container crashed with error

### Step 2: Check Container Logs

```bash
# View recent logs
docker logs servicename

# View last 100 lines
docker logs --tail 100 servicename

# Follow logs in real-time
docker logs -f servicename

# Show timestamps
docker logs -t servicename

# Logs since specific time
docker logs --since 10m servicename
```

### Step 3: Check Health Details

```bash
# Detailed health information
docker inspect servicename --format='{{json .State.Health}}' | jq .

# Just health status and last check
docker inspect servicename --format='{{.State.Health.Status}} - Last: {{range .State.Health.Log}}{{.ExitCode}} {{.Output}}{{end}}'
```

### Step 4: Check Network Connectivity

```bash
# Test if service responds locally
curl -s http://localhost:PORT/

# Check what ports are exposed
docker port servicename

# List networks
docker network ls

# Check network connectivity
docker exec servicename ping -c 2 another-service
```

### Step 5: Check Inside the Container

```bash
# Open shell in container
docker exec -it servicename sh
# or
docker exec -it servicename bash

# Check listening ports inside container
docker exec servicename netstat -tlnp
# or
docker exec servicename ss -tlnp

# Check running processes
docker exec servicename ps aux

# Check environment variables
docker exec servicename env
```

---

## Stack-Specific Debugging

### Hoppscotch

```bash
# Check both containers
docker ps -a --filter "name=hoppscotch"

# Main container logs
docker logs hoppscotch

# Database logs
docker logs hoppscotch-db

# Check database connection
docker exec hoppscotch-db pg_isready -U hoppscotch

# Check ports inside container
docker exec hoppscotch netstat -tlnp
```

**Common issues:**
- Port 80 not found → Image changed to multi-port (3000, 3100, 3170)
- Database connection refused → Check `hoppscotch-db` is healthy
- Migration failed → Check logs for Prisma errors

### Grafana

```bash
docker logs grafana
docker exec grafana grafana-cli plugins ls
```

**Common issues:**
- Plugin installation failed → Check disk space
- Dashboard not loading → Check data source connectivity

### n8n

```bash
docker logs n8n
docker exec n8n n8n list:workflow
```

**Common issues:**
- Webhook not working → Check tunnel routing and ports

### Portainer

```bash
docker logs portainer
curl -s http://localhost:9090/api/status
```

### Infisical

```bash
docker logs infisical
docker logs infisical-db
docker exec infisical-db pg_isready -U infisical
```

### Database Containers (PostgreSQL)

```bash
# Connect to database
docker exec -it servicename-db psql -U username -d database

# Check database size
docker exec servicename-db psql -U username -d database -c "SELECT pg_size_pretty(pg_database_size('database'));"

# List tables
docker exec servicename-db psql -U username -d database -c "\dt"
```

---

## Common Issues and Solutions

### Container keeps restarting

```bash
# Check exit code
docker inspect servicename --format='{{.State.ExitCode}}'

# Check last logs before crash
docker logs --tail 50 servicename

# Check restart count
docker inspect servicename --format='{{.RestartCount}}'
```

**Solutions:**
- Exit code 137: Out of memory → Increase server RAM or limit other containers
- Exit code 1: Application error → Check logs for specific error
- Exit code 0 with restart: Health check failing → Check health endpoint

### Service unreachable via browser

1. **Check container is running:** `docker ps --filter "name=servicename"`
2. **Check local connectivity:** `curl http://localhost:PORT/`
3. **Check tunnel routing:** Verify `services.yaml` port matches docker-compose
4. **Check Cloudflare Access:** Clear browser cache, try incognito

### Database connection issues

```bash
# Check database container is healthy
docker ps --filter "name=servicename-db"

# Test connection from app container
docker exec servicename ping -c 2 servicename-db

# Check database logs
docker logs servicename-db
```

### Disk space issues

```bash
# Check disk usage
df -h

# Check Docker disk usage
docker system df

# Clean unused Docker resources
docker system prune -a --volumes  # CAREFUL: removes unused data!
```

### Memory issues

```bash
# Check memory usage
free -h

# Check per-container memory
docker stats --no-stream

# Check container memory limit
docker inspect servicename --format='{{.HostConfig.Memory}}'
```

---

## Service Ports Reference

| Service | Host Port | Container Port | Health Endpoint |
|---------|-----------|----------------|-----------------|
| Hoppscotch | 3003 | 3000 | `/` |
| Grafana | 3001 | 3000 | `/api/health` |
| n8n | 5678 | 5678 | `/healthz` |
| Portainer | 9090 | 9000 | `/api/status` |
| Uptime Kuma | 3005 | 3001 | `/` |
| Infisical | 8070 | 8080 | `/api/status` |
| MinIO | 9000/9001 | 9000/9001 | `/minio/health/live` |
| Metabase | 3002 | 3000 | `/api/health` |
| Kestra | 8080 | 8080 | `/api/v1/health` |
| IT Tools | 8081 | 80 | `/` |
| Wetty | 3006 | 3000 | `/` |
| CloudBeaver | 8978 | 8978 | `/` |
| Excalidraw | 3004 | 80 | `/` |
| Draw.io | 3007 | 8080 | `/` |
| Mage | 6789 | 6789 | `/api/status` |
| Marimo | 2718 | 2718 | `/` |
| Redpanda Console | 8082 | 8080 | `/admin/health` |

---

## Restarting Services

```bash
# Restart single container
docker restart servicename

# Restart with updated config (after docker-compose changes)
cd /opt/docker-server/stacks/servicename
docker compose up -d --force-recreate

# Stop and remove container (keeps data volumes)
docker compose down
docker compose up -d
```

---

## Useful One-Liners

```bash
# Show all unhealthy containers
docker ps --filter "health=unhealthy"

# Show containers that restarted recently
docker ps --filter "status=restarting"

# Get IP address of a container
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' servicename

# Show real-time resource usage
docker stats

# Follow logs for all containers
docker compose logs -f

# Check which container uses most disk
docker system df -v | head -30
```
