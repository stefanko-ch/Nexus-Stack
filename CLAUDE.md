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
- **OS**: Ubuntu 24.04 (ARM-based cax11 servers)
- **Shell**: Bash scripts
- **Build Tool**: Make

## Project Structure

```
Nexus-Stack/
├── Makefile                    # Main entry point - all commands here
├── README.md                   # User documentation
├── AGENTS.md                   # Agent instructions (this file)
├── services.yaml               # Service metadata (subdomain, port, description, image)
├── .github/
│   └── workflows/             # GitHub Actions workflows
│       ├── initial-setup.yaml  # Initial setup (triggers Control Plane + Spin Up)
│       ├── setup-control-plane.yaml # Setup Control Plane only
│       ├── spin-up.yml         # Spin-up workflow (re-deploy after teardown)
│       ├── teardown.yml        # Teardown workflow (stops infrastructure)
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
├── control-panel/              # Control Plane (Cloudflare Pages)
│   ├── pages/                  # Pages frontend + Functions
│   │   ├── index.html          # Frontend UI
│   │   ├── functions/api/      # API endpoints (deploy, teardown, status, etc.)
│   │   └── nexus-logo-green.png
│   └── worker/                 # Scheduled teardown Worker
│       └── src/index.js        # Worker logic (deployed via Terraform)
├── scripts/
│   ├── deploy.sh               # Post-infrastructure deployment script
│   ├── init-r2-state.sh        # R2 bucket + credentials setup
│   ├── setup-control-panel-secrets.sh  # Control Panel secrets setup
│   ├── generate-info-page.sh   # Info page generation
│   └── check-control-panel-env.sh
└── docs/                       # Documentation
    ├── CONTRIBUTING.md         # Contribution guidelines
    ├── setup-guide.md          # Setup instructions
    └── stacks.md               # Stack documentation
```

## Key Commands

**Deployment (via GitHub Actions only):**
```bash
gh workflow run initial-setup.yaml  # First-time setup
gh workflow run spin-up.yml         # Re-deploy after teardown
gh workflow run teardown.yml        # Stop infrastructure
gh workflow run destroy-all.yml -f confirm=DESTROY  # Full cleanup
```

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

1. **Verify ARM64 compatibility BEFORE creating the stack:**
   - **CRITICAL:** Nexus-Stack runs on ARM64 servers (cax31 = Ampere Altra)
   - Check if the Docker image supports ARM64:
     ```bash
     docker manifest inspect <image>:<tag> | grep -A5 architecture
     ```
   - If only `amd64` is listed → image does NOT support ARM64
   - **Solutions if ARM64 not supported:**
     - Option A: Find an alternative image that supports ARM64
     - Option B: Create a custom Dockerfile that builds from ARM64 base (Python, Node.js, etc.)
     - Option C: Use `docker buildx` with multi-platform builds
   - **Example (Soda Core):** Official image only supports amd64 → custom Dockerfile with `python:3.11-slim` + `pip install soda-core-postgres`

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
   - **Exception:** Only use `latest` for non-critical standalone tools (drawio, it-tools, wetty, code-server, jupyter, marimo, adminer, excalidraw)
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
   - Add auto-setup API call in `scripts/deploy.sh` (Step 6/6)
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

**Example auto-setup (in deploy.sh):**
```bash
if echo "$ENABLED_SERVICES" | grep -qw "myservice" && [ -n "$MYSERVICE_PASS" ]; then
    echo "  Configuring MyService admin..."
    # Call service's admin setup API
    curl -s -X POST 'http://localhost:PORT/api/setup' \
        -d '{"username":"admin","password":"'$MYSERVICE_PASS'"}'
fi
```

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

**Only one feature branch at a time.** Always finish the current feature branch (PR merged or closed) before starting a new one. Working on multiple branches in parallel leads to cross-contamination of changes, merge conflicts, and confusion about which changes belong where. If a second task comes up, either add it to the current branch (if related) or wait until the current PR is merged.

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

### Responding to PR Review Comments

**Critically evaluate every Copilot review comment before acting on it.** Copilot suggestions are automated and may be wrong, unnecessary, or counterproductive. Do NOT blindly apply every suggestion. For each comment:
- Does the suggestion actually improve the code, or is it cosmetic/pedantic?
- Could the suggestion introduce a new bug or break existing logic?
- Does it conflict with the project's patterns or architecture?
- Is the concern valid in this specific context, or is it generic advice?

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
- Server runs **Ubuntu 24.04**
- Always test changes before committing
- Keep README.md updated when adding features
- Follow best security practices to protect sensitive data
- Follow Conventional Commits for all commit messages
- Always adapt documentation to reflect any changes made

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
