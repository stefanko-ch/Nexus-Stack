# Nexus-Stack - Agent Instructions

## Language

**Always respond and generate code in English**, even if the user writes in German or another language. This includes:
- Code comments
- Variable/function names
- Commit messages
- Documentation
- README content

## Emoji Usage

**Use emojis sparingly and only where they add value:**
- Avoid excessive emojis in commit messages, PR descriptions, and documentation
- Use emojis only when they improve readability or highlight important sections
- Prefer clear, descriptive text over emoji-heavy content
- In code comments: Use emojis only for visual markers (e.g., `// ⚠️ Warning:` or `// ✅ Success`)
- In documentation: Use emojis sparingly in section headers or callouts

## No Advertising or Branding

**NEVER add advertising or branding footers to any content:**
- NO "Generated with Claude Code" or similar footers in PRs, Issues, or documentation
- NO links to Anthropic, Claude, or any AI tool providers
- NO promotional language or branding
- NO `Co-Authored-By` trailers in commit messages (e.g., `Co-Authored-By: Claude ...`)
- The user pays for the service and should not see advertising in their project content
- Keep all content professional and focused on the technical task at hand

## Project Overview

Nexus-Stack is an **open-source infrastructure-as-code project** that provides one-command deployment of Docker services on Hetzner Cloud with Cloudflare Zero Trust protection. It achieves **zero open ports** by routing all traffic through Cloudflare Tunnel.

**Target users**: Developers who want to self-host Docker applications securely with minimal effort.

## Tech Stack

- **Infrastructure**: OpenTofu (Terraform-compatible)
- **Cloud Provider**: Hetzner Cloud
- **Security**: Cloudflare Zero Trust, Cloudflare Tunnel, Cloudflare Access
- **Containers**: Docker, Docker Compose
- **OS**: Ubuntu 26.04 LTS (x86 `cx43` servers; see the stack-addition notes for the ARM history)
- **Shell**: Bash scripts
- **Build Tool**: Make

## Project Structure

```
Nexus-Stack/
├── Makefile                    # Main entry point - all commands here
├── README.md                   # User documentation
├── CLAUDE.md                   # Agent instructions (this file)
├── AGENTS.md                   # Deprecated stub, points at CLAUDE.md
├── services.yaml               # Service metadata (subdomain, port, description, image)
├── .github/
│   ├── actions/               # Composite actions shared by the workflows
│   │   ├── nexus-bootstrap/    # OpenTofu + uv + cloudflared + SSH key + R2 creds
│   │   └── nexus-config-tfvars/ # Generates tofu/stack/config.tfvars
│   └── workflows/             # GitHub Actions workflows
│       ├── initial-setup.yaml  # Initial setup (triggers Control Plane + Spin Up)
│       ├── setup-control-plane.yaml # Setup Control Plane only
│       ├── spin-up.yml         # Spin-up workflow (re-deploy after teardown)
│       ├── teardown.yml        # Teardown workflow (stops infrastructure)
│       ├── spin-up-snapshot.yml # Spin-up restoring from a Hetzner disk snapshot
│       ├── teardown-snapshot.yml # Teardown that snapshots the disk first
│       ├── destroy-all.yml     # Destroy workflow (full cleanup)
│       └── release.yml         # Release workflow
├── tofu/                       # OpenTofu/Terraform configuration
│   ├── backend.hcl             # Shared R2 backend configuration
│   ├── config.tfvars.example.dev   # Template for local dev (not for production)
│   ├── stack/                  # Server, tunnel, services state
│   │   ├── main.tf             # Core infrastructure (server, tunnel, DNS)
│   │   ├── variables.tf        # Input variable definitions
│   │   ├── outputs.tf          # Output definitions
│   │   └── providers.tf        # Provider configuration
│   └── control-plane/          # Control Plane state (separate)
│       ├── main.tf             # Pages, Worker, D1, Access
│       ├── variables.tf        # Input variable definitions
│       ├── outputs.tf          # Output definitions
│       └── providers.tf        # Provider configuration
├── stacks/                     # Docker Compose stacks (one folder per service)
│   └── <service>/docker-compose.yml
├── control-plane/              # Control Plane (Astro + Cloudflare Pages)
│   ├── src/                    # Astro source files
│   │   ├── layouts/Layout.astro  # Shared layout (header, footer, nav)
│   │   ├── components/         # Reusable Astro components (Header, Toast)
│   │   ├── pages/              # Page routes (index, stacks, database, etc.)
│   │   ├── lib/categories.ts   # Shared category constants
│   │   └── styles/global.css   # Global styles
│   ├── public/                 # Static assets (logo)
│   ├── functions/api/          # Cloudflare Pages Functions (API endpoints)
│   ├── worker/                 # Scheduled teardown Worker
│   │   └── src/index.js        # Worker logic (deployed via Terraform)
│   ├── astro.config.mjs        # Astro configuration
│   ├── package.json            # Dependencies (astro)
│   └── schema.sql              # D1 database schema
├── scripts/
│   ├── init-r2-state.sh        # R2 bucket + credentials setup
│   ├── setup-control-panel-secrets.sh  # Control Panel secrets setup
│   └── check-control-panel-env.sh
│   # Note: deploy.sh removed in Phase 4c (#505) — replaced by
│   # `python -m nexus_deploy run-pipeline`. spin-up.yml calls the
│   # Python entrypoint directly.
└── docs/                       # Documentation (single source of truth for nexus-stack.ch)
    ├── CONTRIBUTING.md         # Contribution guidelines (GitHub-only, not synced)
    ├── user-guides/            # End-user guides (students/participants using a Control Plane)
    │   └── control-plane.md    # Control Plane web UI walkthrough
    ├── admin-guides/           # Operator/self-hoster guides
    │   ├── setup-guide.md      # Initial infrastructure setup
    │   ├── debugging.md        # Log inspection, systemd, Docker
    │   ├── ssh-access.md       # SSH via Cloudflare Tunnel
    │   ├── snapshot-lifecycle.md # Disk-snapshot teardown/spin-up: switching + rollback
    │   ├── troubleshooting.md  # Common operational issues
    │   └── docs-website-sync.md # How these docs sync to nexus-stack.ch
    ├── stacks/                 # Per-service documentation (one .md per service)
    └── tutorials/              # Tutorials and walkthroughs
```

## Key Commands

**Deployment (via GitHub Actions only):**
```bash
gh workflow run initial-setup.yaml  # First-time setup
gh workflow run spin-up.yml         # Re-deploy after teardown
gh workflow run teardown.yml        # Stop infrastructure
gh workflow run destroy-all.yml -f confirm=DESTROY  # Full cleanup
```

**Two lifecycles.** `spin-up.yml` / `teardown.yml` destroy and rebuild from
`ubuntu-26.04`. `spin-up-snapshot.yml` / `teardown-snapshot.yml` take a Hetzner
disk snapshot and restore from it — faster, and the only path that preserves
data for stacks outside the five the R2 layer covers.

Which pair a stack uses is the D1 config value `lifecycle_mode`
(`rebuild` | `snapshot`), read by the Control Plane and settable from its
Settings page. In the Actions UI the pairs appear as **Lifecycle: …
(Rebuild)** and **Lifecycle: … (Snapshot)**. The value was originally
`legacy`; it was renamed because the pair is a permanent fallback rather than
something deprecated, and `schema.sql` migrates existing rows on every
Control Plane deploy. **Never dispatch the two pairs at the same stack
interchangeably**: the rebuild teardown runs an
untargeted `tofu destroy` that regenerates all 81 service credentials, and the
epoch guard then correctly refuses any existing snapshot. That is why it is one
config key rather than one per workflow.

See [docs/admin-guides/snapshot-lifecycle.md](docs/admin-guides/snapshot-lifecycle.md)
for switching and rollback, and `docs/proposals/0002-hetzner-disk-snapshots.md`
for the design.

**Debugging Tools (local, requires SSH):**
```bash
ssh nexus                          # SSH into server via Cloudflare Tunnel
ssh nexus "docker ps"              # Show running containers
ssh nexus "docker logs <service>"  # View container logs
```

> ⚠️ **Note:** Deployment is only supported via GitHub Actions workflows.

## Development Guidelines

### Code Style

- **Terraform/OpenTofu**: Use 2-space indentation, descriptive resource names with `${local.resource_prefix}` prefix
- **Bash scripts**: Use `set -e`, include colored output with emoji for user feedback
- **Docker Compose**: Always use `networks: app-network` (external), include `restart: unless-stopped`
- **Comments**: Use section headers with `# =====` separators for major sections

### Security Principles

1. **Never commit secrets** - API tokens, passwords go in `config.tfvars` (gitignored)
2. **Zero open ports** - All traffic through Cloudflare Tunnel, no direct SSH
3. **Cloudflare Access** - All services behind email OTP authentication by default
4. **Minimal permissions** - Cloudflare API tokens should have only required permissions
5. **Centralized secrets** - All service passwords generated by OpenTofu, pushed to Infisical
6. **NEVER print secrets to logs** - This is CRITICAL for public repositories:
   - Never `echo` passwords, tokens, API keys, or secrets
   - Never print API responses that may contain tokens
   - Never include credentials in error messages
   - Use `(from Infisical)` or `Credentials available in Infisical` instead
   - Always use `::add-mask::` in GitHub Actions for dynamic secrets
   - Bad: `echo "Password: $ADMIN_PASS"`
   - Good: `echo "Credentials available in Infisical"`

### Error Handling Principles

**NEVER silently swallow errors in critical operations.** This is especially important for infrastructure destruction and deployment.

1. **Critical operations must fail loudly:**
   - Infrastructure destroy commands (Terraform/OpenTofu)
   - Resource deletion operations
   - Deployment steps that affect running services

2. **Bad patterns to AVOID:**
   ```bash
   # BAD - hides all errors, workflow stays green even on failure
   tofu destroy -var-file=config.tfvars -auto-approve 2>/dev/null || echo "No state"

   # BAD - suppresses errors, continues on failure
   tofu destroy -var-file=config.tfvars -auto-approve || echo "Failed"
   ```

3. **Good patterns to USE:**
   ```bash
   # GOOD - fails workflow on error with clear message
   if ! tofu destroy -var-file=config.tfvars -auto-approve; then
     echo "❌ ERROR: Failed to destroy infrastructure"
     echo "   Resources may still be running - check logs above"
     exit 1
   fi
   echo "✅ Infrastructure destroyed successfully"
   ```

4. **When `|| echo` is acceptable:**
   - Reading optional configuration values: `tofu output -raw optional_value 2>/dev/null || echo ""`
   - Checking if resources exist: `ssh-keygen -R "$HOST" 2>/dev/null || true`
   - Logging operations that shouldn't break the flow: `echo "..." >> "$LOG_FILE" 2>/dev/null || true`

5. **Why this matters:**
   - Silent failures can leave infrastructure running → unexpected costs
   - Users need clear feedback when operations fail
   - Green checkmarks on failed workflows are misleading and dangerous
   - Errors provide critical debugging information

### Service Account Naming Convention

All service accounts MUST use the `nexus-` prefix to prevent default username guessing:
- Database users: `nexus-postgres`, `nexus-kestra`, `nexus-infisical`, `nexus-hoppscotch`, `nexus-soda`, `nexus-meltano`
- Service admin accounts: `nexus-minio`, `nexus-redpanda`
- NEVER use default names like `admin`, `postgres`, `root`, or the service name alone
- Application admin usernames use the configurable `$ADMIN_USERNAME` variable (from `variables.tf`)

### Adding New Stacks

When adding a new Docker stack, **all locations must be updated**:

1. **Verify image compatibility BEFORE creating the stack:**
   - Nexus-Stack defaults to **x86 servers (`cx43`, Intel-shared, 8 vCPU / 16 GB RAM / 160 GB) in `hel1`** since 2026-05. Switched permanently from ARM (`cax31`) for two reasons:
     (a) Hetzner ARM EU capacity has been unavailable for an extended period, and
     (b) Hetzner's pricing flipped — ARM is now ~40% more expensive than equivalent x86 (was ~50% cheaper at project start).
     Bumped from `cpx32` (AMD, 4 vCPU / 8 GB) to `cx43` later in 2026-05 because the 40+ Docker stacks workload (JVM-heavy services + Postgres + DuckDB) sustains better with the larger Intel box, and the price delta is small enough to be cost-optimized for the use case.
   - **Required:** the image must support `linux/amd64`. Check via:
     ```bash
     docker manifest inspect <image>:<tag> | grep -A5 architecture
     ```
   - **Strongly preferred:** also support `linux/arm64`. Multi-arch images keep the door open for an easy ARM revert if Hetzner's pricing flips back, and let contributors test locally on Apple Silicon without an emulator.
   - **If only one arch is listed and it's not amd64:**
     - Option A: Find an alternative upstream image with amd64 support
     - Option B: Create a custom Dockerfile from a multi-arch base (`python:3.11-slim`, `debian:bookworm-slim`, `node:lts-slim`) so the rebuilt image works on both arches
     - Option C: Use `docker buildx` with `--platform linux/amd64,linux/arm64`
   - **Example (Soda Core):** Official image only supports amd64 → custom Dockerfile with `python:3.11-slim` + `pip install soda-core-postgres` (the pip-on-multi-arch-base pattern produces an arch-correct build automatically).

2. **Check for port conflicts:**
   - **CRITICAL:** Before assigning ports, check that they are not already in use by other services
   - Search all existing ports in services.yaml:
     ```bash
     grep -E "^\s+(port:|[a-z-]+:) [0-9]+" services.yaml | awk '{print $2}' | sort -n
     ```
   - If a port conflict exists, choose different ports (both for web UI and tcp_ports)
   - **Common conflicts:**
     - MinIO uses 9000 (S3) and 9001 (Console)
     - PostgreSQL uses 5432
     - Redis uses 6379
   - Use Docker port mapping if the service requires specific internal ports:
     ```yaml
     ports:
       - "9002:9001"  # Host port 9002 → Container port 9001
     ```

3. **Pin Docker image versions:**
   - **CRITICAL:** Always use specific version tags, NOT `latest`
   - **Exception:** Only use `latest` for non-critical standalone tools (drawio, it-tools, wetty, code-server, jupyter, marimo, adminer, excalidraw, evidence). Common property: presentation-layer or dev-tool, no persistent state beyond cache; upstream publishes no semver tags (only `:latest`), so digest pinning would still require manual update on every refresh and offers no real predictability win.
   - **Pin versions for:**
     - All data storage services (databases, object storage, data lakes)
     - Services with persistent state or databases
     - Services that are part of data pipelines
   - **How to find stable versions:**
     - Check Docker Hub tags page for the image
     - Use GitHub releases page for official version numbers
     - Prefer stable releases over alpha/beta (exception: if only alpha exists, pin to specific alpha version)
   - **Example pinned versions:**
     ```yaml
     # Good - pinned version
     image: "treeverse/lakefs:1.73.0"

     # Bad - unpredictable updates
     image: "treeverse/lakefs:latest"
     ```
   - Update both `services.yaml` and `stacks/*/docker-compose.yml` with the same version

4. **Create the Docker Compose file:**
   - Create `stacks/<stack-name>/docker-compose.yml`
   - Use unique port (verified in step 2)
   - Include `networks: app-network` (external: true)
   - Add descriptive header comment with service URL
   - **IMPORTANT: Each stack should have its own dedicated resources (database, Redis, etc.)**
     - Do NOT share databases between stacks (e.g., don't use the shared PostgreSQL for new stacks)
     - Each service requiring a database should include its own database container in the compose file
     - Use internal networks (e.g., `<service>-internal`) to isolate service-specific resources
     - Example: Meltano has `meltano-db`, Soda has `soda-db`, each independent

5. **Register the service in services.yaml:**
   - Add to `services` map in `services.yaml` (root directory)
   - Use matching port number from docker-compose.yml
   - Use pinned image version from step 3
   - No `enabled` field needed - D1 manages runtime state

6. **Update README.md:**
   - Add stack badge in the "Available Stacks" badges section
   - Add row to the "Available Stacks" table with description and website link
   - **IMPORTANT:** Badge order MUST match table order - badges should appear in the same sequence as rows in the table
   - **IMPORTANT:** Update the stack count in the heading `## Available Stacks (N)` to reflect the new total

7. **Update docs/stacks/:**
   - Create `docs/stacks/<stack-name>.md` with badge, description, and configuration details
   - Include port, subdomain, default credentials (if any), and special setup instructions
   - Add entry to the Docker Image Versions table in `docs/stacks/README.md`
   - Add link to the Stack Documentation table in `docs/stacks/README.md`

8. **Add admin credentials (if service has admin UI):**
   - Add `random_password.<service>_admin` resource in `tofu/stack/main.tf`
   - Add password to `secrets` output in `tofu/stack/outputs.tf`
   - Add auto-setup hook to `src/nexus_deploy/services.py` (the
     services-configure phase dispatch loop)
   - Add password to Infisical secrets push payload
   - Verify credentials are pushed to Infisical

**Badge format:**
```markdown
![StackName](https://img.shields.io/badge/StackName-COLOR?logo=LOGO&logoColor=white)
```
Find logos at [simpleicons.org](https://simpleicons.org/)

**Example service entry (services.yaml):**
```yaml
portainer:
  subdomain: "portainer"       # → https://portainer.domain.com
  port: 9090                   # Must match docker-compose port
  public: false                # false = requires Cloudflare Access login
  description: "Docker container management UI"
  image: "portainer/portainer-ce:lts"
```

> **Note:** The `enabled` field is NOT in services.yaml - it's managed by D1 (Control Plane).
> Core services have `core: true` and are always enabled.

**Example password resource (in main.tf):**
```hcl
resource "random_password" "myservice_admin" {
  length  = 24
  special = false
}
```

**Example auto-setup (in `src/nexus_deploy/services.py`):**

Add an entry to the `_SERVICE_HOOKS` registry — the
`services-configure` phase dispatches each enabled service's hook in
one SSH round-trip. Hooks are pure-rendering functions: they produce
the bash that runs on the server. See existing hooks
(`_render_filestash_setup`, `_render_redpanda_setup`, etc.) for
the pattern + per-hook unit tests in `tests/unit/test_services.py`.

> **Note:** The `services.yaml` file defines service metadata (subdomain, port, image), while `stacks/` contains Docker Compose definitions. Both must be in sync. Runtime state (enabled/disabled) is stored in Cloudflare D1 and managed via the Control Plane.

### Sensitive Data Handling

- `*.tfvars` files are gitignored (except `*.example`)
- `terraform.tfstate` contains sensitive data - gitignored
- Never echo API tokens or secrets in scripts
- Use `sensitive = true` for Terraform variables containing secrets
- All service passwords are stored in Infisical after deployment

## Build & Validation

### Prerequisites Check
```bash
# Verify tools are installed
which tofu cloudflared docker
```

### Pre-commit hooks (REQUIRED before Python edits)

The repo ships a `.pre-commit-config.yaml` that runs `ruff format`,
`ruff check`, `mypy`, and `shellcheck` on every commit. **The hook is
not active until installed locally** — fresh clones don't get it
automatically. Without it, formatter drift (e.g. long f-strings, set
comprehensions) lands on the branch, then CI fails on the `ruff format
--check` step with a "would reformat N files" error.

Install once per clone:
```bash
# If `core.hooksPath` is set redundantly (points at default), unset first:
git config --get core.hooksPath && git config --unset-all core.hooksPath
uv run pre-commit install
```

Verify it's wired up:
```bash
ls -la .git/hooks/pre-commit  # should exist and be executable
```

**Don't rely on memory** — `ruff check` (which catches lint rules) and
`ruff format --check` (which catches whitespace/line-length drift) are
SEPARATE checks. CI runs both; running only `ruff check` locally will
miss formatter issues. The pre-commit hook is the only reliable gate.

If a commit must skip a hook (rare, document why):
```bash
SKIP=ruff-format git commit -m "..."
```

### Test Infrastructure Changes
```bash
cd tofu && tofu plan -var-file=config.tfvars
```

### Validate Terraform Syntax
```bash
cd tofu && tofu validate
```

### Mandatory Testing

**Every change must be tested before committing.** This includes:
- `cd tofu/stack && tofu plan -var-file=config.tfvars` to verify infrastructure changes
- Deploy via GitHub Actions (`gh workflow run spin-up.yml`)
- Verify services are accessible via their URLs
- Check credentials are available in Infisical
- Test auto-setup worked (login with generated credentials)

### Testing Instructions for the User

**After making changes, ALWAYS provide clear testing instructions to the user:**

1. **Specify the testing method:**
   - Can the user test on the feature branch directly?
   - Is `gh workflow run spin-up.yml` sufficient, or does `initial-setup.yaml` need to be run?
   - Are there any special prerequisites or configurations needed?

2. **Include step-by-step instructions:**
   ```markdown
   ## Testing Instructions

   You can test this change on the feature branch:

   1. Push the feature branch to GitHub (if not already done)
   2. Run the spin-up workflow:
      ```bash
      gh workflow run spin-up.yml --ref feat/your-branch
      ```
   3. Wait for deployment to complete (~5-10 minutes)
   4. Verify the new service:
      - Access https://service.your-domain.com
      - Check credentials in Infisical
      - Test the main functionality
   5. Run teardown when done:
      ```bash
      gh workflow run teardown.yml
      ```
   ```

3. **Mention if a full initial-setup is required:**
   - New Terraform resources (DNS, Tunnel, Access policies) → requires `initial-setup.yaml`
   - Only Docker/config changes → `spin-up.yml` is sufficient
   - Control Plane changes → may need `setup-control-plane.yaml` first

4. **Include verification steps:**
   - What should work after deployment?
   - Where to check logs if something fails?
   - What credentials are needed (and where to find them)?

**Example:**
```markdown
## How to Test

This adds a new internal-only service. You can test it with:

1. Push changes and run spin-up:
   ```bash
   gh workflow run spin-up.yml --ref feat/soda-stack
   ```

2. Wait for deployment, then SSH to the server:
   ```bash
   ssh nexus
   docker exec -it soda soda --version
   ```

3. Verify the database password is in Infisical under `soda_db_password`

No initial-setup needed since this is an internal_only service (no DNS/Tunnel changes).
```

## Debugging Best Practices

**When something doesn't work, think outside the box!**

### 0. Logs First, No Guessing (CRITICAL)

**NEVER speculate or make assumptions. Always check actual logs and facts first.**

When debugging any issue, follow this strict order:

1. **Check logs BEFORE forming any hypothesis:**
   - **GitHub Actions logs**: `gh run view <id> --log-failed` or `--log` with grep
   - **Container logs on server**: `gh run view <id> --log` and search for the service name, or SSH to server for `docker logs <container>`
   - **OpenTofu output**: Check the `Apply infrastructure` step for actual resource state
   - **Cloudflare Tunnel config**: Check the `Install Cloudflare Tunnel` step for ingress rules
   - Read the COMPLETE error message, not just the first line

2. **Verify actual state, don't assume:**
   - Check what env vars are actually set in the container (not what you think they should be)
   - Check if the container is actually running and healthy
   - Check the actual .env file content on the server
   - Check the actual Docker Compose file that was synced to the server
   - Confirm variable values are what you expect them to be

3. **Only after reading logs, analyze:**
   - What is the exact error message?
   - At what exact point does the flow fail?
   - What do the logs say happened vs. what should have happened?

4. **Consult documentation only for specific questions:**
   - "Is env var X supported in version Y?" → check the official docs
   - "What is the correct env var name?" → check the docs
   - Don't research broadly when the logs already tell you the answer

5. **Examples of what NOT to do:**
   - ❌ Researching "why might OAuth fail" without first reading the actual error log
   - ❌ Guessing "Cloudflare Access probably blocks this" without checking container logs
   - ❌ Assuming an env var works without verifying the version supports it
   - ❌ Making multiple speculative fixes without reading what the server actually reports

6. **Examples of proper debugging:**
   - ✅ "OAuth fails → check Woodpecker container logs → see exact error → fix based on what the log says"
   - ✅ "Container unhealthy → check `docker logs woodpecker-server` → see crash reason → fix"
   - ✅ "SSH fails → What IP is being used? → `2a01:4f8:xxxx::/64` → That's a network, not a host! → Fix: append `::1`"

**Rule: No fix attempt without first reading the relevant logs. Facts only, no speculation.**

### 1. Where to Find Logs

| Source | How to access | What it shows |
|--------|--------------|---------------|
| **GitHub Actions** | `gh run view <id> --log` | Full workflow output |
| **Failed steps only** | `gh run view <id> --log-failed` | Only failed step output |
| **Container logs** | SSH to server: `docker logs <container>` | Application-level errors |
| **Docker status** | SSH: `docker ps -a` | Container state (running/exited/unhealthy) |
| **Docker inspect** | SSH: `docker inspect <container>` | Full config, env vars, health check results |
| **Env file on server** | SSH: `cat /opt/docker-server/stacks/<service>/.env` | Actual env vars used |
| **Tunnel config** | grep for "Updated to new configuration" in workflow logs | Actual ingress rules |

### 2. Verify Infrastructure Configuration

Many issues stem from missing or misconfigured Terraform resources. Check:
- All required resources exist (not just the obvious ones)
- Resource dependencies are correctly configured
- Provider-specific requirements are met

### 3. Cloudflare-Specific Gotchas

| Service | Requirement | Common Mistake |
|---------|-------------|----------------|
| **Cloudflare Pages** | Requires `cloudflare_pages_domain` resource | CNAME alone is NOT enough for custom domains |
| **Cloudflare Tunnel** | Requires `cloudflare_tunnel_config` | Just creating tunnel doesn't route traffic |
| **Cloudflare Access** | Requires `cloudflare_access_application` | DNS + tunnel doesn't add authentication |

**Example: Cloudflare Pages Custom Domain**
```hcl
# CNAME record alone does NOT work!
resource "cloudflare_record" "control_plane" {
  name  = "control"
  type  = "CNAME"
  value = "${local.resource_prefix}-control.pages.dev"  # e.g., nexus-stefanko-ch-control.pages.dev
}

# You ALSO need this resource:
resource "cloudflare_pages_domain" "control_plane" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.control_plane.name
  domain       = "control.${var.domain}"
}
```

### 4. Debugging Workflow

1. **Check the logs** - Read them thoroughly, not just "it succeeded"
2. **Verify all resources exist** - Use `tofu state list` to check what was created
3. **Check provider documentation** - Understand ALL required resources
4. **Test the underlying service** - e.g., Pages works at `*.pages.dev` but not custom domain
5. **Only then consider client-side** - DNS cache, browser cache, etc.

### 5. Don't Assume - Verify

- Don't assume DNS propagation delay - use `dig` or `nslookup` to check
- Don't assume "it was created" means "it's configured correctly"
- Don't assume one resource handles everything - many services need multiple resources

## Common Patterns

### Resource Naming
All Hetzner/Cloudflare resources use `${local.resource_prefix}` prefix (derived from domain, e.g., `nexus-stefanko-ch`):
- Server: `nexus-stefanko-ch`
- Firewall: `nexus-stefanko-ch-fw`
- SSH Key: `nexus-stefanko-ch-key`
- Tunnel: `nexus-stefanko-ch`
- Access Apps: `nexus-stefanko-ch <ServiceName>`
- D1 Database: `nexus-stefanko-ch-db`
- Worker: `nexus-stefanko-ch-worker`
- Pages Project: `nexus-stefanko-ch-control`

### Service Configuration
Services are defined in `config.tfvars`:
```hcl
services = {
  service-name = {
    enabled   = true
    subdomain = "app"      # → https://app.domain.com
    port      = 8080       # Must match docker-compose
    public    = false      # false = requires Cloudflare Access login
  }
}
```

### Docker Network
All services must join the external `app-network`:
```yaml
networks:
  app-network:
    external: true
```

### Code Examples (`examples/workspace-seeds/`)

Sample code that ships with Nexus-Stack and gets auto-seeded into every user's Gitea workspace repo on spin-up. **The `_phase_seed` orchestrator phase (in `src/nexus_deploy/orchestrator.py`, delegating to `src/nexus_deploy/seeder.py`) walks `examples/workspace-seeds/` recursively and POSTs each file under the `nexus_seeds/` prefix in the workspace repo via Gitea's contents API**, so `workspace-seeds/kestra/flows/x.yaml` lands at the user repo's `nexus_seeds/kestra/flows/x.yaml`, registered by `system.flow-sync` under namespace `nexus-tutorials`. The `nexus_seeds/` prefix (introduced in #501) keeps Nexus-Stack-managed files visually separated from the user's own course material at the repo root.

When adding or editing seeded examples:

1. **Stay inside `examples/workspace-seeds/`.** Reference material that is *not* meant to land in the workspace repo goes in a sibling directory (e.g. `examples/contributing/`), explicitly labelled "not auto-seeded" in `examples/README.md`.
2. **Two folder conventions, pick the right one:**
   - **Per-stack folder** (e.g. `kestra/flows/`, `kestra/workflows/`) — when the seed is unambiguously tied to one Nexus-Stack and that stack expects to find it at a stack-specific path. Today only `kestra/` qualifies.
   - **Per-consumer-type folder** (e.g. `notebooks/`, `scripts/`, `dbt/`, `sql/`) — when the same files are consumed by *several* stacks (notebooks → Jupyter + Marimo + code-server; SQL → DuckDB + Trino + ClickHouse). New top-level subdirs need a corresponding consumer wired up.
3. **No schedule triggers in seeded Kestra flows.** Seeded flows live on every user stack — a cron trigger fires N times when there are N users, multiplying CloudFront downloads, R2 egress, Databricks Free-Edition quota burn, and Kestra container CPU. Examples are teaching artifacts; users hit **Execute** in the Kestra UI to run them. If you genuinely need a scheduled flow, register it directly via the orchestrator's `_phase_kestra_register` (defined in `src/nexus_deploy/orchestrator.py`, delegating to the `register_flow` helper in `src/nexus_deploy/kestra.py`; the `system.flow-sync` flow is the existing example) — that's infrastructure, not a learning sample, and lives outside `workspace-seeds/`.
4. **Reference Infisical-managed secrets only via `{{ secret('NAME') }}`.** Hardcoding credentials in `examples/` is a public-repo leak. During each spin-up, the orchestrator's `_phase_kestra_secret_sync` (in `src/nexus_deploy/orchestrator.py`, delegating to `src/nexus_deploy/secret_sync.py`) fetches every secret from every Infisical folder, base64-encodes the values, and writes them as `SECRET_<NAME>=<base64>` env-var entries into a delimited block in `stacks/kestra/.env` (look for `BEGIN nexus-secret-sync` in the rendered remote script). Kestra is then `--force-recreate`d so its `EnvVarSecretProvider` loads the new values at startup. `GITEA_TOKEN` is added by the same step as a special case (it's generated post-Gitea-start and isn't in Infisical at the time of the bootstrap push). Net result: seeded flows can reference any Infisical key by name via `{{ secret('NAME') }}` without further setup. Note: this is the OSS-compatible mechanism — the older "POST to /api/v1/secrets/<ns>/<key>" path doesn't exist in Kestra OSS (returns 404; the corresponding GET endpoint reports `readOnly: true`).
5. **Make seed files idempotent.** A user may execute a seeded flow more than once. Either detect pre-existing state and skip, or design the flow so re-runs are safe (overwriting outputs is fine; accumulating side-effects is not).
6. **Existing files in Gitea are never overwritten.** The seed loop uses HTTP `POST` (create-only); it returns 422 for files that already exist and counts them as `SKIPPED`. User edits persist across re-deploys. To ship an updated example, give it a new filename or version-suffix it.

Full details — including the `kestra/flows/` vs `kestra/workflows/` distinction, Kestra namespace derivation from subdirs, and how to add a new per-stack or per-consumer subtype — live in [examples/README.md](examples/README.md).

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/). All commit messages must follow this format:

```
<type>(<scope>): <description>
```

### Types

| Type | Description | Example |
|------|-------------|---------|
| `feat` | New feature | `feat(stacks): Add Apache Spark integration` |
| `fix` | Bug fix | `fix: Correct Grafana port mapping` |
| `refactor` | Code restructuring | `refactor: Simplify deploy script` |
| `docs` | Documentation | `docs: Update installation instructions` |
| `chore` | Maintenance | `chore: Update dependencies` |
| `ci` | CI/CD changes | `ci: Add release workflow` |

### Scopes (optional)

| Scope | Use for |
|-------|---------|
| `stacks` | Docker stack changes |
| `tofu` | OpenTofu/Infrastructure changes |
| `docs` | Documentation |
| `ci` | GitHub Actions / CI |
| `scripts` | Shell scripts |

### Breaking Changes

Add `!` after the type for breaking changes:
```bash
feat!: Change secret management to Vault-only
```

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for full details.

## Git Workflow

**Never commit directly to the `main` branch.** The `main` branch is protected and should only be modified via Pull Requests.

**Never merge Pull Requests.** PRs must go through Copilot code review first. Only create PRs and push commits - the user will merge after review passes.

**Do NOT automatically create Pull Requests.** Wait for the user to explicitly request a PR before creating one. The user may want to make additional changes, test locally, or review the commits first.

**Parallel feature branches are allowed if they touch disjoint files.** Concurrent PRs are fine when each branch operates on a different code area (e.g. one PR on `stacks/metabase/`, another on `control-plane/src/components/`, a third on `src/nexus_deploy/orchestrator.py`). Before starting a new branch, verify the file scope doesn't overlap with any in-flight branch — if it does, finish the existing one (or close it) first, otherwise the second branch will hit a rebase + manual merge-conflict resolution on a file you've already touched.

**Practical guardrails when running parallel branches:**

- Before creating each new branch, `git fetch --prune origin` + check open PRs (`gh pr list --state open`). Confirm none of them touch the same files you're about to.
- Keep each branch single-purpose. Don't start adding new unrelated changes to a branch that's already in review — open a fresh branch instead.
- When one of the parallel PRs merges, the others may need a quick `git fetch && git rebase origin/main` if `main` moved over a file they share (rare with disjoint scopes; common with broad refactors).
- Don't run more than 3-4 PRs in flight at once — Copilot review threads accumulate cognitively, and you (the human) lose track of what's where. Sequential is still the right default for related work.

**Same-file changes still need sequencing.** If two issues both need an edit to the same file (e.g. both modify `compose_runner.py`), do them in one branch as separate commits, or do one branch first and rebase the second after the first merges. Parallel branches racing on the same file are the failure mode the old "one at a time" rule was guarding against — that part is still real.

### Commit and Push Workflow

**When making code changes, follow this workflow:**

1. **After making changes, immediately inform the user** what exactly was changed:
   - Describe the specific files modified
   - Explain what was added, removed, or changed
   - Mention any important details or considerations

2. **Commit the changes immediately** after informing the user:
   - Use conventional commit format: `type(scope): description`
   - Include a detailed commit message explaining what was done
   - Stage only the relevant files

3. **Ask the user before pushing**:
   - After committing, ask: "Soll ich pushen?" or "Should I push?"
   - Wait for explicit confirmation before pushing to remote
   - Do NOT push automatically unless explicitly requested

**Example workflow:**
```
1. Make code changes
2. "I've added a new step to delete R2 bucket in destroy-all.yml workflow..."
3. git commit -m "fix(ci): Add R2 bucket cleanup..."
4. "Soll ich pushen?" / "Should I push?"
5. Wait for user confirmation
6. git push (only if confirmed)
```

### PR Titles for Release Notes

**PR titles are used to generate release notes.** The release pipeline extracts PR titles (not individual commits) to create the changelog. Therefore:

- **PR titles must follow Conventional Commits format**: `type(scope): description`
- The PR title determines the changelog category (Features, Bug Fixes, etc.)
- Individual commits within a PR can be WIP or fix-ups - only the PR title matters

**Examples:**
```
feat(stacks): Add Excalidraw whiteboard stack     → Listed under "🚀 Features"
fix(ci): Use PR titles for release notes          → Listed under "🐛 Bug Fixes"
docs: Update setup guide for R2 state backend     → Listed under "📚 Documentation"
```

**Bad examples (avoid):**
```
Update files                    → No conventional commit prefix
WIP: still working on it        → Not descriptive
Merge branch 'main' into feat   → Merge commits should not be PR titles
```

### Development Workflow

1. Create a feature branch from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feat/my-feature
   ```

2. Make changes and commit with conventional commits:
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   ```

3. Push and create a Pull Request:
   ```bash
   git push origin feat/my-feature
   ```

4. After PR review and merge → Release is created automatically

### Branch Cleanup Rules

**When cleaning up branches, NEVER delete:**
- `main` - Protected main branch
- `release-please--branches--main` - Used by Release Please to create release PRs

The `release-please--branches--main` branch is automatically managed by the Release Please GitHub Action. Deleting it will break the automated release process until a new commit triggers Release Please to recreate it.

**Safe to delete after merge:**
- Feature branches (`feat/*`)
- Fix branches (`fix/*`)
- Documentation branches (`docs/*`)
- Any other temporary development branches

**Sweep for stale merged branches whenever creating a new branch.** Before running `git checkout -b`, check for branches whose PR has already been merged and delete them (local + remote). Prevents the `git branch -a` listing from filling up with zombie branches that were merged days or weeks ago and never cleaned up.

```bash
# At the top of any new-branch workflow, before `git checkout -b`:
git fetch --prune origin
gh pr list --state merged --limit 20 --json number,headRefName,mergedAt
# For every local or remote branch that matches a merged PR's headRefName
# (excluding `main` and `release-please--branches--main`):
git push origin --delete <branch>   # remote
git branch -D <branch>              # local, if present
```

Don't sweep silently — report which branches were deleted in one line so the user sees what happened.

### Responding to PR Review Comments

**Critically evaluate every Copilot review comment before acting on it.** Copilot suggestions are automated and may be wrong, unnecessary, or counterproductive. Do NOT blindly apply every suggestion. For each comment:
- Does the suggestion actually improve the code, or is it cosmetic/pedantic?
- Could the suggestion introduce a new bug or break existing logic?
- Does it conflict with the project's patterns or architecture?
- Is the concern valid in this specific context, or is it generic advice?

Before applying any suggestion that re-adds previously removed code, check `git log -S "<removed code>"` to understand why it was removed. If it was intentionally removed, reject the suggestion and explain why.

Only fix comments that identify genuine issues. Dismiss or explain comments that are incorrect or not applicable.

**When addressing PR review comments, respond directly to each individual comment, not with a summary comment.**

- Use `gh api` to reply to each review comment thread
- Each fix should be addressed with a direct reply to the specific comment
- This creates clear traceability between comments and fixes
- Only use summary comments if explicitly requested by the reviewer

**How to reply directly to a PR review comment:**

```bash
# 1. Get the comment ID from the PR review comments
gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments

# 2. Reply to a specific comment using in_reply_to
gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments \
  -X POST \
  -f body="Fixed in commit abc1234 - description of fix" \
  -F in_reply_to=COMMENT_ID
```

**Example:**
```bash
# Reply to comment ID 2695714963 on PR #97
gh api repos/stefanko-ch/Nexus-Stack/pulls/97/comments \
  -X POST \
  -f body="Fixed in commit 53fa498 - removed redundant text." \
  -F in_reply_to=2695714963
```

**Workflow:**
1. Get all PR review comments: `gh api repos/OWNER/REPO/pulls/PR/comments`
2. Fix each issue in code
3. Commit fixes with descriptive message
4. Reply directly to each comment thread with the commit reference
5. Push changes

### Branch Naming

Use prefixes that match commit types:
- `feat/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `chore/` - Maintenance tasks

## Important Notes

- This is a **public open-source project** - code should be clean, well-documented, and secure
- **Never commit directly to `main`** - always use feature branches and PRs
- Target platform is **macOS** for local development
- Server runs **Ubuntu 26.04 LTS**
- Always test changes before committing
- Keep README.md updated when adding features
- Follow best security practices to protect sensitive data
- Follow Conventional Commits for all commit messages
- Always adapt documentation to reflect any changes made

## Documentation Drift Prevention

**Every PR must be checked for documentation impact.** Before creating or finalizing a PR, verify:

1. **Does this change affect any documentation?** Check:
   - `docs/stacks/*.md` - if a service was added, changed, or removed
   - `docs/admin-guides/setup-guide.md` - if setup steps, secrets, or workflows changed
   - `docs/user-guides/control-plane.md` - if the Control Plane UI or API changed
   - `docs/admin-guides/debugging.md` / `docs/admin-guides/troubleshooting.md` - if debugging steps changed
   - `docs/admin-guides/docs-website-sync.md` - if the sync mechanism changed
   - `README.md` - if architecture, stack count, or overview changed
   - `services.yaml` - if service metadata changed (port, subdomain, image, description)
   - `CLAUDE.md` - if development guidelines or project structure changed

2. **Update affected docs in the same PR.** Never leave docs out of sync - the website at nexus-stack.ch pulls directly from `docs/` and `services.yaml`, so stale docs = stale website.

3. **Keep `.github/copilot-instructions.md` in sync with larger changes.** That file is what GitHub's Copilot PR reviewer uses to check every incoming PR. It describes project-specific conventions, security rules, and "do not flag this" trade-offs. If a change in this PR would invalidate any statement in `.github/copilot-instructions.md` — new naming convention, new stack-addition step, new security rule, an issue getting closed that's referenced there, a convention flipping (e.g. the tutorial-link format change tracked in #456 eventually landing) — update the Copilot instructions in the same PR. Stale instructions turn the reviewer into a noise generator.

4. **Stack count:** If stacks were added or removed, update the count in `README.md` heading `## Available Stacks (N)` and verify badges match the table.

## Documentation Image Syntax

**Never use HTML `<img>` tags in `docs/**/*.md`. Always use markdown `![alt](./assets/foo.png)` syntax.**

Why this matters — there is a concrete failure mode, not a style preference:

- Nexus-Stack documentation is synced to [nexus-stack.ch](https://nexus-stack.ch) by `scripts/fetch-docs.mjs` in the `stefanko-ch/nexus-stack.ch` repo. The website is built with Astro + Starlight.
- Astro only resolves, optimizes, and copies images referenced via markdown `![]()` syntax (it runs them through its content-collection image pipeline → `/_astro/*.webp`).
- HTML `<img src="./assets/foo.png">` tags are passed through unchanged. The `./assets/` relative path then resolves in the browser against the rendered page URL (e.g. `/docs/guides/user-guides/dashboard/assets/foo.png`) — a path that does not exist in the built site.
- Result: pages with HTML `<img>` tags either break the build (if the referenced image also isn't findable by Astro's content pipeline) or render with broken image icons at runtime. This happened in [PR #450](https://github.com/stefanko-ch/Nexus-Stack/pull/450).

**Rules:**

1. **Markdown-only for all `./assets/…` images.** Use `![Descriptive alt text](./assets/filename.png)`. Do not use `<img src="./assets/...">`.
2. **Descriptive alt text, not just the filename.** For accessibility and for the fallback when the image fails to load. `![Scheduled teardown toggle](./assets/settings-scheduled-teardown.png)` — not `![settings-scheduled-teardown](…)`.
3. **Do not use `style="width: N%"` or similar inline styles.** Starlight applies responsive image styling automatically. If you genuinely need a narrow image (icon, button), keep the source image itself small — do not rely on CSS width constraints.
4. **Assets go in the guide's own `assets/` folder** (e.g. `docs/user-guides/assets/`, `docs/admin-guides/assets/`). The website's `fetch-docs.mjs` syncs these into the matching subfolder next to the markdown so relative `./assets/…` paths resolve at build time.

## Documentation Internal Links

**For relative links between markdown files in `docs/**/*.md`, always include the `.md` extension.** Use `[Monitoring](./monitoring.md)`, not `[Monitoring](./monitoring)`.

Why this matters — same editor-vs-site mismatch as the image-syntax rule, different symptom:

- Starlight renders each `.md` file as a directory with a trailing slash: `docs/user-guides/control-plane.md` → `/docs/guides/user-guides/control-plane/`.
- A browser-side relative link `./monitoring` from that URL resolves to `/docs/guides/user-guides/control-plane/monitoring` — a child path that **does not exist**. The actual sibling page is at `/docs/guides/user-guides/monitoring/`.
- Result: every extension-less `./foo` link between guides returns 404 on the website, while looking fine in the GitHub viewer (which resolves file-relative, not URL-relative). This is a silent drift — the broken links only show up when a user actually clicks through on the live site. Happened in [PR #454](https://github.com/stefanko-ch/Nexus-Stack/pull/454).

**Rule:** Write `[text](./sibling.md)`. Astro/Starlight strips the `.md` at build time and resolves against the source location, producing the correct URL. GitHub's markdown viewer also follows `.md` links correctly. Both renderers happy, one source of truth.

This applies to **every** relative markdown-to-markdown link in `docs/`, not just user-guides.

## Closing Issues via PRs

**When creating a Pull Request, always check if there is a corresponding Issue that should be closed by the PR.**

Before creating a PR:
1. Search for related issues using `gh issue list` or by checking the repository issues
2. Look for issues that match the PR's purpose (feature requests, bug reports, etc.)
3. If a matching issue is found, include the closing keyword in the PR description

Use keywords in PR descriptions to automatically close issues when merged:

```markdown
Closes #7
Closes #4
Fixes #3
```

This creates a clear link between PRs and the issues they resolve and helps maintain project organization.

## Creating GitHub Issues and Pull Requests

**Problem:** Heredoc syntax (`<< 'EOF'`) in terminal commands causes parsing issues and garbled output.

**Solution:** Use the `create_file` tool to write the body file, then run `gh` command separately:

```bash
# Step 1: Use create_file tool to write body
create_file("/tmp/pr-body.md", "## Summary\n\nDescription here...")

# Step 2: Run gh command in terminal
gh pr create --title "feat: Title here" --body-file /tmp/pr-body.md

# Step 3: Clean up
rm /tmp/pr-body.md
```

**NEVER use heredoc in terminal:**
```bash
# BAD - causes garbled output in this environment
cat > /tmp/body.md << 'EOF'
content
EOF

# GOOD - use create_file tool instead
# (Assume /tmp/body.md was created with the create_file tool)
gh pr create --title "feat: Title here" --body-file /tmp/body.md
rm /tmp/body.md
```

**Important:**
- Always use `create_file` tool for multiline content (PR body, issue body)
- Use `/tmp/` directory for temp files (not in repo)
- Always clean up temp files after with `rm`
- The `--body-file` flag works reliably with files created by `create_file`
