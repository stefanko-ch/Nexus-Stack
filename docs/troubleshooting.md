# Troubleshooting Guide

## Firewall Management

### External TCP Access Not Working

**Symptoms:**
- Connection timeout when accessing services via external TCP ports (e.g., RedPanda 9092, PostgreSQL 5432, MinIO 9000)
- Databricks notebooks fail with connection errors
- `docker ps` shows ports are not mapped to host (e.g., `5432/tcp` instead of `0.0.0.0:5432->5432/tcp`)

**Root Cause:**
The infrastructure was deployed before firewall rules were activated in the Control Plane, or firewall rules were changed after deployment.

**Solution:**
Re-run the Spin Up workflow to regenerate firewall override files and restart services:

```bash
gh workflow run spin-up.yml
```

This triggers `deploy.sh` which:
1. Fetches active firewall rules from OpenTofu state
2. Generates `docker-compose.firewall.yml` override files for each service
3. Restarts services with port mappings (e.g., `9092:19092` for RedPanda, `5432:5432` for PostgreSQL)
4. Configures SASL authentication for RedPanda external listener

**Verification:**
After re-deployment, verify ports are mapped:

```bash
ssh nexus "docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep -E '(redpanda|postgres|minio)'"
```

Expected output:
```
postgres           0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
redpanda           0.0.0.0:9092->19092/tcp, [::]:9092->19092/tcp, ...
minio              0.0.0.0:9000->9000/tcp, [::]:9000->9000/tcp, ...
```

### PostgreSQL Healthcheck Failing

**Symptoms:**
- PostgreSQL container logs show repeated errors: `FATAL: database "nexus-postgres" does not exist`
- Container may be stuck in unhealthy state

**Root Cause:**
The healthcheck command `pg_isready -U nexus-postgres` defaults to connecting to a database with the same name as the user. Since the user is `nexus-postgres` but the database is named `postgres`, the healthcheck fails.

**Solution:**
This has been fixed. If you encounter this issue, pull the latest changes and re-deploy:

```bash
git pull origin main
gh workflow run spin-up.yml
```

The healthcheck now correctly specifies the database: `pg_isready -U nexus-postgres -d postgres`

### RedPanda SASL Authentication Not Configured

**Symptoms:**
- RedPanda logs don't show SASL user creation
- Kafka clients fail with authentication errors when connecting externally
- Internal connections (kafka-ui) work fine

**Root Cause:**
The firewall override file wasn't generated, so the `RP_BOOTSTRAP_USER` environment variable was never set.

**Solution:**
Re-run the Spin Up workflow to generate the firewall override with SASL configuration:

```bash
gh workflow run spin-up.yml
```

**Verification:**
Check that the firewall override exists and includes SASL config:

```bash
ssh nexus "cat /opt/docker-server/stacks/redpanda/docker-compose.firewall.yml"
```

Expected output should include:
```yaml
environment:
  RP_BOOTSTRAP_USER: "nexus-redpanda:XXXX"
```

## General Tips

### SSH Access Issues

If you get "Operation timed out" when trying to SSH:
1. Ensure `cloudflared` is installed: `brew install cloudflare/cloudflare/cloudflared` (macOS) or download from [Cloudflare](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)
2. Your SSH config should include `ProxyCommand cloudflared access ssh --hostname %h`
3. You'll need to authenticate via browser (email OTP) on first connection

### Checking Service Status

View running containers:
```bash
ssh nexus "docker ps"
```

View logs for a specific service:
```bash
ssh nexus "docker logs SERVICE_NAME --tail 100"
```

Check if firewall override files exist:
```bash
ssh nexus "ls -la /opt/docker-server/stacks/*/docker-compose.firewall.yml"
```

### Re-deploying After Configuration Changes

After making changes in the Control Plane (firewall rules, service toggles):
1. Run `gh workflow run spin-up.yml` to apply changes
2. Wait for deployment to complete (~5-10 minutes)
3. Verify changes with `ssh nexus "docker ps"` or check service URLs

For infrastructure changes (domain, server size, Cloudflare settings):
1. Update `tofu/stack/config.tfvars`
2. Commit and push changes
3. Run `gh workflow run spin-up.yml`
