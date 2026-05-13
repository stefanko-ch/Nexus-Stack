---
title: "Setup Guide"
description: "Complete installation and configuration guide for Nexus-Stack"
order: 1
---

# 🚀 Nexus Setup Guide

This guide walks you through the complete setup of Nexus Stack.

> ⚠️ **This project uses GitHub Actions exclusively. Local deployment is not supported.**

---

## 📋 Prerequisites

### Accounts

- [ ] **Hetzner Cloud Account** — [Sign up](https://console.hetzner.cloud/)
- [ ] **Cloudflare Account** — [Sign up](https://dash.cloudflare.com/sign-up)
- [ ] **Domain on Cloudflare** — DNS must be managed by Cloudflare
- [ ] **GitHub Account** — Repository for the project

### Optional Accounts

- [ ] **[Resend](https://resend.com)** — For email notifications (credentials, status updates)
- [ ] **[Docker Hub](https://hub.docker.com)** — Increases pull rate limits for Docker images

---

## 1️⃣ Create Hetzner Project

> ⚠️ Projects can only be created manually — not via API/OpenTofu.

1. Go to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Click **"+ New Project"**
3. Name it `Nexus` (or whatever you prefer)
4. Open the project

> 💡 **Tip — check Hetzner stock before you deploy.** Hetzner periodically runs out of specific instance types (`cx43`, `cx53`, `cpx42`, `cpx52`, `cpx62`) in specific datacenters. The [Hetzner Cloud Console](https://console.hetzner.cloud/) → **Add Server** UI greys out out-of-stock `<type>:<location>` combinations live, so a 10-second glance before your first `gh workflow run initial-setup.yaml` is worth it — if your default region (`hel1`) is dry for all five types, switch `SERVER_LOCATION` to one that's green (see [Optional Repository Variables](#optional-repository-variables) below). The capacity-fallback step in the workflow uses the same Hetzner data, so what the Console shows is exactly what spin-up will pick.

### Generate API Token

1. In your project, go to **Security** → **API Tokens**
2. Click **"Generate API Token"**
3. Name: `nexus-tofu`
4. Permissions: **Read & Write**
5. **Copy the token** — you'll only see it once!

---

## 2️⃣ Configure Cloudflare

### Get Zone ID and Account ID

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Select your domain
3. On the **Overview** page, scroll down to find:
   - **Zone ID** (right sidebar)
   - **Account ID** (right sidebar)

### Enable Services R2, Workers and Zero Trust


1. In the left sidebar, go to **Storage & Databases** → **R2 Object Storage**
2. Click **"Enable R2"** and complete the checkout flow (free tier is sufficient)
3. In the left sidebar, go to Workers & Pages
4. If this is your first visit, you will be prompted to create a *.workers.dev subdomain
5. Choose a subdomain name and click "Set up"
6. In the left sidebar, go to Zero Trust
7. Click "Get Started", enter a team name, purchase the free plan


### Create API Token

1. Go to **My Profile** → **API Tokens**
2. Click **"Create Token"**
3. Use template: **"Create Custom Token"**
4. Token name: `nexus-stack`
5. **Permissions:**

   | Scope | Resource | Permission |
   |-------|----------|------------|
   | Account | Cloudflare Tunnel | Edit |
   | Account | Access: Apps and Policies | Edit |
   | Account | Access: Service Tokens | Edit |
   | Account | Access: Organizations, Identity Providers, and Groups | Edit |
   | Account | Workers R2 Storage | Edit |
   | Account | Workers KV Storage | Edit |
   | Account | D1 | Edit |
   | Account | Workers Scripts | Edit |
   | Account | Cloudflare Pages | Edit |
   | User | API Tokens | Edit |
   | Zone | DNS | Edit |
   | Zone | Zone | Read |

   > **Note:**
   > - "Workers R2 Storage" is required for the remote state backend
   > - "Workers KV Storage" is required for the Workers KV namespace
   > - "D1" is required for the database used by the Control Plane
   > - "Workers Scripts" is required for the scheduled teardown worker
   > - "Cloudflare Pages" is required for the Control Plane
   > - "Access: Organizations" is required for revoking Zero Trust sessions during teardown
   > - "Access: Service Tokens" enables headless SSH authentication for CI/CD
   > - "User API Tokens" is required for the init script to create scoped R2 credentials

6. **Account Resources:** Include → All accounts (or specific)
7. **Zone Resources:** Include → Specific Zone → Your domain
8. Click **"Continue to summary"** → **"Create Token"**
9. **Copy the token!**

---

## 3️⃣ Configure GitHub Secrets

Add these secrets to your GitHub repository:

**Settings → Secrets and variables → Actions → New repository secret**

### Required Secrets

| Secret Name | Source | Description |
|-------------|--------|-------------|
| `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard | API access |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard | Account ID |
| `CLOUDFLARE_ZONE_ID` | Cloudflare dashboard | Zone ID |
| `HCLOUD_TOKEN` | Hetzner console | API token |
| `DOMAIN` | Your domain | e.g. `example.com` |
| `TF_VAR_admin_email` | Your email | Admin - full access including SSH |

### Optional Secrets

| Secret Name | Description |
|-------------|-------------|
| `GH_SECRETS_TOKEN` | GitHub PAT for R2 auto-save and Cloudflare runtime (see below) |
| `TF_VAR_user_email` | User - all services except SSH |
| `RESEND_API_KEY` | Email notifications via Resend |
| `DOCKERHUB_USERNAME` | Docker Hub username (higher pull limits) |
| `DOCKERHUB_TOKEN` | Docker Hub access token |

### S3-Persistence Secrets (RFC 0001)

Persistence moved from Hetzner block storage to R2 in RFC 0001. **Zero new operator-set secrets required** — the workflows derive everything from already-existing secrets and conventions:

- **`PERSISTENCE_S3_ENDPOINT`** is computed inline as `https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com`.
- **`PERSISTENCE_S3_REGION`** is always `auto` (R2 doesn't use regions).
- **`PERSISTENCE_S3_BUCKET`** follows the convention `nexus-<domain-slug>-persistence` and is created idempotently by `setup-control-plane.yaml` the same way the data bucket is.
- **`R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`** are the unified R2 token credentials already set by `init-r2-state.sh` (used by the Tofu state backend too).

Optional secrets (only set if you want to override defaults):

| Secret Name | Default | Why you'd override |
|-------------|---------|---------------------|
| `NEXUS_S3_PERSISTENCE` | `"true"` (workflow fallback) | Set explicitly to `"false"` to bypass persistence for an experiment. |
| `PERSISTENCE_STACK_SLUG` | `github.event.repository.name` | Set if you want the manifest written under a different slug (e.g. for Education-mode forks that share a persistence bucket layout). |

#### GH_SECRETS_TOKEN

This token allows the initial setup workflow to automatically save R2 credentials as GitHub Secrets. It is also used as the runtime `GITHUB_TOKEN` in Cloudflare (for the scheduled teardown worker and Control Plane), so it must be able to dispatch workflows. Without it, you must manually copy the credentials from the workflow logs after the first run, and Cloudflare-based automation that triggers GitHub Actions will fail.

**How to create:**
1. Go to **GitHub** → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click **"Generate new token"**
3. **Repository access**: Select your Nexus-Stack repository
4. **Permissions** (Repository permissions):
   - **Secrets** → **Read and write**
   - **Actions** → **Read and write** (required so Cloudflare workers can dispatch workflows)
5. Copy the token and save it as `GH_SECRETS_TOKEN` in your repository secrets

### Optional Repository Variables

**Settings → Secrets and variables → Actions → Variables tab**

| Variable Name | Default | Description |
|---------------|---------|-------------|
| `SERVER_TYPE` | `cx43` | Hetzner server type. Default `cx43` (Intel-shared, 8 vCPU / 16 GB RAM / 160 GB) is sized for the 40+ Docker stacks scenario. Smaller alternatives: `cpx32` (AMD, 4 vCPU / 8 GB), `cx32` (Intel, 4 vCPU / 8 GB). ARM variants (`cax*`) supported but currently more expensive — see [Optional Repository Variables](#optional-repository-variables) below. |
| `SERVER_LOCATION` | `hel1` | Hetzner datacenter region for the VM. EU options: `hel1` (Helsinki), `fsn1` (Falkenstein), `nbg1` (Nuremberg). US option: `ash` (Ashburn). Change if your preferred region has availability issues — see the troubleshooting note below. |
| `HETZNER_S3_LOCATION` | `fsn1` | Hetzner Object Storage region (independent from server location). Propagated to OpenTofu and all S3 operations automatically. Only change if your buckets are in a different region. |

> **Note:** Hetzner server availability fluctuates per region and instance type — both ARM (`cax*`) and x86 (`cx*` / `cpx*`) can hit `resource_unavailable` during capacity crunches. The spin-up workflow's `Select Hetzner capacity` step already walks a 15-pair fallback list (`cx43`, `cx53`, `cpx42`, `cpx52`, `cpx62` across `hel1`/`fsn1`/`nbg1` — see [hetzner_capacity.py](../../src/nexus_deploy/hetzner_capacity.py)), so a typical capacity crunch is handled automatically. If even those 15 combinations are dry, check the [Hetzner Cloud Console](https://console.hetzner.cloud/) → **Add Server** UI for what's currently green and override `SERVER_PREFERENCES` (repo variable) accordingly. Common availability: `hel1` (Helsinki) and `fsn1` (Falkenstein) usually have the best stock for `cx43`; `nbg1` (Nuremberg) and `ash` (US-East) can be alternatives.

---

## 4️⃣ Deploy via GitHub Actions

### Initial Setup

Run the initial setup workflow:

```bash
# Core services only (infisical, mailpit, info)
gh workflow run initial-setup.yaml

# With additional services pre-selected
gh workflow run initial-setup.yaml -f enabled_services="grafana,n8n,portainer"
```

Or via GitHub UI:
1. Go to **Actions** → **Initial Setup**
2. Click **Run workflow**
3. *(Optional)* Enter comma-separated services in `enabled_services` field

**Available services:** `grafana`, `n8n`, `portainer`, `uptime-kuma`, `minio`, `metabase`, `kestra`, `it-tools`, `wetty`, `cloudbeaver`, `excalidraw`, `drawio`, `mage`, `marimo`, `redpanda`, `redpanda-console`

> **Note:** Core services (infisical, mailpit, info) are always enabled automatically.

On **first run**, the pipeline will:
1. Create the R2 bucket automatically
2. Generate R2 API credentials
3. Deploy the Control Plane
4. Trigger the spin-up workflow

> ⚠️ **Important:** R2 credentials are generated on the first run. If `GH_SECRETS_TOKEN` is configured (see [Optional Secrets](#optional-secrets)), they are saved automatically. Otherwise, copy them from the workflow logs and save them manually.

### Add R2 Credentials as Secrets

If `GH_SECRETS_TOKEN` is configured, this step is automatic. Otherwise, after the first deploy, add these two secrets manually:

| Secret Name | Source |
|-------------|--------|
| `R2_ACCESS_KEY_ID` | Shown in first deploy logs |
| `R2_SECRET_ACCESS_KEY` | Shown in first deploy logs |

Once saved, all future deployments will use these credentials automatically.

---

## 5️⃣ Access Your Services

After deployment, your services are available at:

| Service | URL |
|---------|-----|
| **Control Plane** | `https://control.yourdomain.com` |
| **Dashboard** | `https://info.yourdomain.com` |
| **Grafana** | `https://grafana.yourdomain.com` |
| **Portainer** | `https://portainer.yourdomain.com` |
| **IT-Tools** | `https://it-tools.yourdomain.com` |

### First Login

1. Open any service URL
2. Cloudflare Access will prompt for your email
3. Enter the email you configured in `TF_VAR_admin_email`
4. Check your inbox for the verification code
5. Enter the code — you're in!

### View Credentials

Use the Control Plane to view or email credentials:
- Open `https://control.yourdomain.com`
- Click **"Email Credentials"** to receive them via email
- Or check **Infisical** at `https://infisical.yourdomain.com`

---

## 6️⃣ GitHub Actions Workflows

| Workflow | Command | Confirmation | Description |
|----------|---------|--------------|-------------|
| Initial Setup | `gh workflow run initial-setup.yaml [-f enabled_services="..."]` | None | One-time setup (Control Plane + Spin Up) |
| Setup Control Plane | `gh workflow run setup-control-plane.yaml` | None | Setup Control Plane only |
| Spin Up | `gh workflow run spin-up.yml` | None | Re-create infrastructure after teardown |
| Teardown | `gh workflow run teardown.yml` | None | Teardown infra (reversible) |
| Destroy All | `gh workflow run destroy-all.yml -f confirm=DESTROY` | Required | Delete everything |

### Control Plane

Manage your infrastructure via the web interface at `https://control.YOUR_DOMAIN`:

- ⚡ **Spin Up / Teardown** - Start and stop infrastructure with one click
- 🧩 **Services** - Enable/disable services dynamically
- ⏰ **Scheduled Teardown** - Auto-shutdown to save costs
- 📧 **Email Credentials** - Send login credentials to your inbox

---

## 7️⃣ SSH Access (Optional)

SSH access is available for debugging purposes. All SSH traffic goes through Cloudflare Tunnel.

For detailed instructions on setting up SSH access, including:
- Getting the SSH key from Infisical
- Handling changing host keys after server recreation
- Service Token authentication for CI/CD

See the **[SSH Access Guide](ssh-access.md)**.

---

## ⚙️ Optional Configuration

### Auto-Shutdown Policy

By default, users cannot disable the automatic daily teardown feature via the Control Plane. This ensures cost control for shared environments (e.g., student labs).

**To change this behavior**, edit `tofu/control-plane/variables.tf` or set via environment variable:

```hcl
# Allow users to disable auto-shutdown
allow_disable_auto_shutdown = true
```

**Default behavior** (`false`):
- Toggle switch is visible but grayed out
- Users can see if auto-shutdown is enabled
- Users can delay teardown (within the daily limit, see below)
- Users cannot disable auto-shutdown entirely

**Permissive behavior** (`true`):
- Users have full control over auto-shutdown
- Suitable for personal deployments or trusted environments

After changing this setting, re-deploy the Control Plane:
```bash
gh workflow run setup-control-plane.yaml
```

#### Teardown Delay Limits

By default, users can delay each scheduled teardown by **4 hours** at a time, with a maximum of **3 extensions per UTC day**. Each extension is recorded in the Control Plane's audit log with the requesting user's email.

To customize, edit `tofu/control-plane/variables.tf`:

```hcl
max_delay_hours        = 4   # Maximum hours per single delay request
max_extensions_per_day = 3   # Maximum delay requests per UTC day per user
```

Or set via environment variable:

```bash
TF_VAR_max_delay_hours=2 TF_VAR_max_extensions_per_day=5 gh workflow run setup-control-plane.yaml
```

See [Control Plane User Guide](../user-guides/control-plane.md#administrator-policy-infrastructure-level) for details.

### Hetzner Object Storage for LakeFS

LakeFS can use **Hetzner Object Storage** as a backend instead of local storage. This provides scalable, durable storage for data lake versioning.

**When to use:**
- Production data lake environments
- Data that exceeds server disk capacity
- Need for data persistence beyond server teardown

**Setup Steps:**

1. **Create S3 credentials in Hetzner Console:**
   - Go to [Hetzner Cloud Console](https://console.hetzner.cloud/)
   - Navigate to **Storage** → **Object Storage**
   - Click **"S3 Credentials"** → **"Generate Credentials"**
   - Save the **Access Key** and **Secret Key**

2. **Add credentials to GitHub Secrets:**
   ```
   HETZNER_OBJECT_STORAGE_ACCESS_KEY = <your-access-key>
   HETZNER_OBJECT_STORAGE_SECRET_KEY = <your-secret-key>
   ```

3. **Deploy infrastructure:**
   The bucket and configuration are handled automatically by GitHub Actions.

**What happens:**
- ✅ LakeFS automatically configures Hetzner S3 as blockstore
- ✅ Default `hetzner-object-storage` repository created with S3 backend
- ✅ All data persists in Hetzner Object Storage

**Without configuration:**
- ⚠️ LakeFS falls back to local filesystem storage
- ⚠️ Default `local-storage` repository created (data lost on teardown)

---

## 🔧 Troubleshooting

### "Tunnel not connecting"

Check GitHub Actions logs for the spin-up workflow. The tunnel may take a few minutes to become active.

### "Permission denied"

Make sure your email matches `TF_VAR_admin_email` in GitHub Secrets.

### "Service not accessible"

1. Check Control Plane status at `https://control.yourdomain.com`
2. Verify the service is enabled
3. Check if infrastructure is running (may be torn down)

### Need more help?

For in-depth debugging including container logs, health checks, and service-specific troubleshooting, see the **[Debugging Guide](debugging.md)**.

---

## 📧 Email Notifications via Resend (Optional)

After deployment, Nexus-Stack can automatically send you an email with all service credentials.

### Setup Steps

1. **Create Resend Account** at [resend.com](https://resend.com)
2. **Add Your Domain** in Resend Dashboard → **Domains**
3. **Verify Domain** by adding DNS records to Cloudflare:

**SPF Record (TXT):**
```
Type: TXT
Name: @
Content: v=spf1 include:resend.com ~all
```

**DKIM Record (TXT):**
```
Type: TXT
Name: resend._domainkey
Content: [provided by Resend]
```

4. **Create API Key** in Resend Dashboard → **API Keys**
5. **Add to GitHub Secrets:**
   ```bash
   gh secret set RESEND_API_KEY --body "re_xxxxxxxxxxxxx"
   ```

---

## 🐳 Docker Hub Credentials (Optional)

Docker Hub limits anonymous image pulls to **100 pulls per 6 hours per IP**. Adding credentials increases this to 200 pulls/6h.

### Setup

1. **Create Docker Hub Access Token:**
   - Go to https://hub.docker.com/settings/security
   - Click **"New Access Token"**
   - Permissions: **Read**
   - **Copy the token**

2. **Set GitHub Secrets:**
   ```bash
   gh secret set DOCKERHUB_USERNAME --body "your-username"
   gh secret set DOCKERHUB_TOKEN --body "dckr_pat_xxxxx"
   ```

---

## 🌐 Website Documentation Sync (Optional)

Documentation in `docs/` can be synced to [nexus-stack.ch](https://nexus-stack.ch) when changes are pushed to `main`. This is handled by the `sync-docs-site.yml` workflow and only runs on the original repository (not on forks).

See [Website Sync Guide](docs-website-sync.md) for setup instructions. Sync requires a Cloudflare Deploy Hook URL stored as `WEBSITE_DEPLOY_HOOK` secret and the `WEBSITE_SYNC_ENABLED` repository variable set to `true`.

## Kestra ↔ Gitea bi-directional flow sync

When the `kestra` service is enabled the orchestrator registers three system-namespace flows that sync flow definitions between Kestra and the user's Gitea workspace fork.

### Two-namespace model

Flows live in two distinct Kestra namespaces, each tied to a separate path in the Gitea fork:

| Kestra namespace | Gitea path in fork | Meaning |
|---|---|---|
| `nexus-tutorials.*` | `nexus_seeds/kestra/flows/` | **Seeded reference flows** shipped by Nexus-Stack. Read-mostly from the student's perspective. NEVER pushed back from the UI (would corrupt the upstream tutorial baseline). |
| `my-flows.*` | `kestra/flows/` | **Student's own work** — clones of seeded flows, new flows. UI-edits in this namespace auto-push to Git every 10 min. |

The `nexus_seeds/` prefix is reserved for Nexus-Stack-shipped content; user-authored flows live at the repo root under `kestra/flows/` to make the ownership distinction visible at a glance in the Gitea fork tree.

### The three system flows

| Flow | Direction | Trigger | Purpose |
|---|---|---|---|
| `system.git-sync` | Gitea → Kestra | once at spin-up | Pulls namespace files (SQL, scripts, queries) from `nexus_seeds/kestra/workflows/` into Kestra's namespace storage |
| `system.flow-sync` | Gitea → Kestra | once at spin-up | Two tasks in one flow: `sync-seeds` pulls `nexus_seeds/kestra/flows/` → `nexus-tutorials.*`; `sync-user` pulls `kestra/flows/` → `my-flows.*`. Both `delete: true`, separate namespaces ensure no interference. |
| `system.flow-export` | Kestra → Gitea | every 10 minutes | Pushes `my-flows.*` only to `kestra/flows/`. Excludes `nexus-tutorials.*` (protects seeds) and `system.*` (echo-prevention). |

### Design rationale

**Pull direction (`git-sync` + `flow-sync`) runs only at spin-up, not on a schedule.** The previous form (`cron: */15`) caused two distinct problems:

1. **Silent overwrite of UI edits.** `SyncFlows` with `delete: true` reconciles Kestra's target namespaces to whatever is in Git every tick. A student editing a flow in the Kestra UI had a 15-minute window before their changes vanished — invisible data loss, no error log.
2. **Ping-pong with the export direction.** A pull running on a 15-min schedule combined with a push running on any schedule would chase each other's commits.

**Steady-state source of truth:**
- For *in-session edits in `my-flows.*`* → the Kestra UI (auto-pushed to Gitea via `flow-export`).
- For *cross-stack restore* → Gitea (the persistence-bucket snapshot covers Kestra's Postgres DB; `flow-sync` re-hydrates Kestra at the next spin-up from Gitea as canonical source).
- For *seeded tutorial flows in `nexus-tutorials.*`* → Git is canonical (the upstream Nexus-Stack repo seeded them). UI-edits there are preserved via DB-snapshot but **not** via Git, and `flow-sync` at the next spin-up will reconcile them away. The copy-before-edit workflow exists to avoid this.

### Loop diagram

```
                  ┌─────────────────────────────────────────┐
                  │  Nexus-Stack repo (upstream)            │
                  │  examples/workspace-seeds/kestra/flows/ │
                  └────────────────┬────────────────────────┘
                                   │
                                   ▼  (POSTed by _phase_seed at first deploy)
                  ┌─────────────────────────────────────────┐
                  │  Gitea fork                             │
                  │  ├── nexus_seeds/kestra/flows/  (seeds) │◀──┐
                  │  └── kestra/flows/             (user)   │   │
                  └────────────────┬───────────────┬────────┘   │
                                   │               ▲           │
                  [Spin-up: flow-sync, 2 tasks]   │           │
                                   │               │           │
                                   ▼               │           │
                  ┌─────────────────────────────────────────┐  │
                  │  Kestra                                 │  │
                  │  ├── nexus-tutorials.*  (read-mostly)   │  │
                  │  └── my-flows.*         (UI-editable)  ─┼──┘
                  │                          every 10 min,  │
                  │                          via flow-export │
                  └─────────────────────────────────────────┘
```

### `flow-export` specifics

- **Cadence:** `cron: "*/10 * * * *"` (every 10 minutes). A stack crash loses at most ~10 minutes of student work in `my-flows.*`. Faster (every 5 min) would multiply commits + R2 egress for marginal recovery; slower (hourly) would lose unacceptable amounts.
- **Source namespace:** `my-flows` only. The PushFlows plugin has no exclude-list, so positive-only namespace scoping is the only way to (a) prevent the exporter from pushing itself (`system.*` echo-loop) AND (b) protect `nexus-tutorials.*` seeds from getting overwritten with student edits.
- **`delete: false`:** a UI-side delete does *not* propagate to Git. To permanently delete a `my-flows.*` flow, the operator commits the removal directly in the Gitea fork; the next `flow-sync` (at next spin-up) drops it from Kestra.
- **Commit identity:** `Kestra Auto-Export <kestra@nexus-stack.local>` (synthetic, never a real user). The Gitea push log still attributes the push to whoever owns the admin token, but Git blame stays clean.
- **Conflict behaviour:** `REJECTED_NONFASTFORWARD` is fail-loud — visible as an execution failure in the Kestra UI, manually resolvable by an operator. Happens when someone commits directly to the fork between two export ticks.

### What students see in the Gitea fork

Two directories under the fork:

```
<fork-root>/
├── nexus_seeds/
│   └── kestra/
│       ├── flows/                         ← seeded tutorial flows
│       │   └── nexus-tutorials/
│       │       └── r2-taxi-pipeline.yml
│       └── workflows/                     ← namespace files (SQL/scripts)
└── kestra/
    └── flows/                             ← student's own auto-exported flows
        └── my-flows/
            └── r2-taxi-experiment.yml     ← auto-commit every ~10 min
```

The `system/` directory is **never** in either tree — those flows are infrastructure (regenerated per deploy).

See [user-guides/kestra-flow-editing.md](../user-guides/kestra-flow-editing.md) for the recommended student-side workflow (copy a seeded flow into `my-flows` before editing).

## 📚 Next Steps

- Enable/disable services via Control Plane
- Check Grafana for logs and metrics
- Set up alerts in Uptime Kuma
- Store secrets in Infisical
