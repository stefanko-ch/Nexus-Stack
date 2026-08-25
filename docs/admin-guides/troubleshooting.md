---
title: "Troubleshooting"
description: "Common issues and solutions for Nexus-Stack"
order: 5
---

# Troubleshooting Guide

## First stop: open Portainer

Before SSH-ing into the box or hunting through GitHub Actions logs, open Portainer at `https://portainer.<your-domain>`. It's a [core service](../stacks/portainer.md) — always running, never an opt-in — exactly so you can reach it when something else is broken.

Portainer surfaces the things you're most likely to need:

| Symptom | Where to look in Portainer |
|---|---|
| Service web UI returns 502 / Bad Gateway | Containers → `<service-name>` → check **Status** column. `Restarting` or `Exited` → click into it → **Logs** tab |
| Container restarting repeatedly / exited with code 137 / `docker inspect` shows `OOMKilled: true` | Containers → `<service-name>` → **Stats** tab → memory graph against `deploy.resources.limits.memory` from the compose |
| Image pull failed during a fresh deploy | Images → search the failing image name → if missing, the worker never pulled it (likely auth / network) |
| Port collision after enabling a new service | Networks → `app-network` → cross-check the listed containers' published ports |
| A container won't start and the compose looks fine | Containers → `<name>` → **Inspect** → look at the actual env vars Docker injected vs the `.env` file you expected |

If Portainer itself is the broken thing (rare — it's a single Go binary, no DB), fall back to SSH and the rest of this guide.

> ℹ️ **Not every "running" container shows a green "healthy" badge.** Some stacks intentionally omit a `healthcheck:` block — typically because the upstream image is too minimal to support a shell-based probe (no `sh`/`curl`/`wget` available), or because reachability is verified externally via the Cloudflare Tunnel front-door instead. Docker reports those containers as just `running` (no health decoration). That's expected; only an actually-coloured **orange "unhealthy"** badge or a `Restarting`/`Exited` status indicates a real problem. If you need to know which specific stacks are in this category, check each `stacks/<name>/docker-compose.yml` for the presence or absence of `healthcheck:`.

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

This triggers `python -m nexus_deploy run-pipeline` which:
1. Fetches active firewall rules from OpenTofu state
2. Generates `docker-compose.firewall.yml` override files for each service (the firewall-configure phase)
3. Restarts services with port mappings (e.g., `9092:19092` for RedPanda, `5432:5432` for PostgreSQL) via the compose-up phase
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

## Hetzner Capacity / `resource_unavailable`

**Symptom:** the `Apply infrastructure` step in the workflow fails with a Hetzner API error like:

```
Error: server type cx43 is not available in hel1
```

or, more generically, a `resource_unavailable` rejection during `tofu apply`.

**Root cause:** Hetzner sells out of specific instance types in specific datacenters during capacity crunches. Both ARM (`cax*`) and x86 (`cx*` / `cpx*`) are affected; the situation can change hour-by-hour.

### Automatic fallback (default since #536)

The `Select Hetzner capacity` step that runs *before* `Apply infrastructure` queries Hetzner's Cloud API (`/v1/server_types` to resolve type-name to internal ID, then `/v1/datacenters` for per-datacenter live availability keyed by those IDs) and picks the first available `<server_type>:<location>` pair from a preference list. The default list — `cx43`, `cx53`, `cpx42`, `cpx52`, `cpx62`, each across `hel1`/`fsn1`/`nbg1` (15 combinations, see [src/nexus_deploy/hetzner_capacity.py](../../src/nexus_deploy/hetzner_capacity.py)) — covers three EU regions across five shared-CPU tiers (cheapest first, Intel→AMD silicon failover), so a typical capacity crunch is handled without operator intervention. The order keeps the historical project-default region (`hel1`) first so a fresh install without `SERVER_PREFERENCES` lands in the same location (`hel1`) as before this feature was added. The actual datacenter within that location (`hel1-dc2`, etc.) is still chosen by Hetzner — `server_location` only pins the location, not a specific DC.

You can see what the step picked in the workflow log. The lines mirror the default preference list above (or whatever override is configured), one entry per pair, in priority order:

```
✓ select-capacity: chose cx43:fsn1
  ✗ 1. cx43:hel1
  → 2. cx43:fsn1
  ✓ 3. cx43:nbg1
  ✓ 4. cx53:hel1
  ✓ 5. cx53:fsn1
  ...
```

`✗` = sold out, `✓` = available, `→` = picked.

### When every preference is out of stock

If every entry in the preference list is sold out, the step fails the workflow with the per-pair status block AND a pointer to the Hetzner Cloud Console. To unblock:

1. Open the [Hetzner Cloud Console](https://console.hetzner.cloud/) → your project → **Add Server**. The create-server UI greys out out-of-stock `<type>:<location>` combinations live, so you immediately see what's available right now. (The Hetzner API the workflow queries is the same data source — but the Console adds it up visually.)
2. Override the preference list by setting `SERVER_PREFERENCES` in your GitHub repository's variables (Settings → Secrets and variables → Actions → Variables → `SERVER_PREFERENCES`) to a comma-separated list, e.g. `cpx62:fsn1, cpx62:nbg1, cx53:hel1`. The first available pair wins, so order entries by preference.
3. Re-run the workflow.

### Operator overrides

| Variable | Effect |
|---|---|
| `SERVER_PREFERENCES` (repo variable, comma list) | Highest priority. `cx43:fsn1, cpx52:nbg1, cpx62:hel1` etc. |
| `server_preferences = "..."` line in `config.tfvars` | Used if `SERVER_PREFERENCES` is unset. |
| `SERVER_TYPE` + `SERVER_LOCATION` (legacy single pair) | Used if neither of the above is set. Effectively a 1-element preference list — the workflow still hard-fails when that one pair is out of stock; widen to a list to get capacity-fallback. |
| Built-in default | Last resort — see list above. |

### Local-dev / dry-run

When `HCLOUD_TOKEN` is not set in the environment (e.g. running the CLI locally without a Hetzner account), the step soft-skips with a stderr warning and leaves `config.tfvars` untouched. The deploy then proceeds with whatever pair is already in the file.

### Why the fallback exists

Hetzner ARM (`cax*`) availability has been chronically constrained since early 2026 and is now ~40% MORE expensive than equivalent x86 (was ~50% cheaper at project start), so the default list excludes ARM entirely. If you need ARM, add it explicitly: `SERVER_PREFERENCES = "cax31:fsn1, cax31:nbg1, cx43:fsn1"`.

## Ubuntu 26.04 and uutils coreutils

Ubuntu 26.04 replaced GNU coreutils with the Rust reimplementation
[uutils](https://uutils.github.io/coreutils/) as its default userland.
Around 80 utilities changed implementation; `cp`, `mv` and `rm` stayed
GNU.

They are close, not identical. Two things to know when a deploy fails
on 26.04 in a way it never did on 24.04:

**Error messages differ in shape.** GNU names the offending path —
`install: cannot stat '/dev/stdin': No such file or directory`. uutils
is terser and may print only `install: No such file or directory`. If
you are looking at a message with no path in it, that alone is a hint
about which implementation produced it.

**Passing a device path where a file is expected can fail.** The
spin-up failure that surfaced this wrote the rclone config with
`install -m 600 /dev/stdin <<'EOF'`, asking `install` to resolve a
*path* to a heredoc. That aborted the restore before it produced any
output, so the workflow log showed one line and nothing else.

The fix, and the pattern to prefer whenever you write a file that
holds credentials:

```bash
mkdir -p "$HOME/.config/rclone"
TMP=$(mktemp "$HOME/.config/rclone/.rclone.conf.XXXXXX")
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<'EOF'
...
EOF
mv -fT "$TMP" "$HOME/.config/rclone/rclone.conf"
```

Four things this gets right, and each of them is a way the shorter
forms go wrong:

- **`cat` reads file descriptor 0** and performs no path lookup, so it
  cannot fail the way `install /dev/stdin` did.
- **Mode 0600 from the first byte.** `mktemp` creates with that mode by
  construction and `mv` is a rename, so the mode survives. A plain
  redirect would create the file 0644.
- **No symlink-follow.** `mktemp` opens `O_EXCL` under a name that did
  not exist, and `mv` *replaces* a symlink at the destination rather
  than writing through it. A `rm -f` followed by a redirect leaves a
  window in which the destination can be re-pointed.
- **Atomic for readers.** The consumer sees the old file or the new
  one, never a half-written one left by a session that died mid-write.
- **`-T` on the `mv`.** Without it, a destination that happens to be a
  *directory* makes `mv` move the temp file inside it rather than
  replacing it — and the `trap` then cleans a path that no longer holds
  the file, leaving the credentials sitting in `rclone.conf/`. `-T`
  forces file semantics for every destination shape. It exists on GNU
  and uutils; BSD `mv` has no equivalent, which matters only if you
  reuse this pattern outside Linux.

The `trap` matters specifically because the temp file holds
credentials: without it, every failed run strands one under a fresh
name.

**Where else to look.** Any rendered remote script that shells out to
coreutils is a candidate. Bash-heavy paths in this project are the
deploy pipeline, the rendered `s3_persistence` snapshot and restore
scripts, and the per-service configure hooks. Failures there tend to be
quiet — wrong output rather than a non-zero exit — so a green step is
not proof.

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
