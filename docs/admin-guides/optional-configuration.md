---
title: "Optional Configuration"
description: "Settings a stack works without: the auto-shutdown policy, Hetzner Object Storage for LakeFS, email via Resend, Docker Hub credentials, the website sync"
order: 9
---

# Optional Configuration

Nothing on this page is needed for a working stack. Each section is independent; do the ones you want after the [Setup Guide](./setup-guide.md).


## Auto-Shutdown Policy

By default, users cannot disable the automatic daily teardown feature via the Control Plane. This ensures cost control for shared environments (e.g., student labs).

**To change this behavior**, edit `tofu/control-plane/variables.tf` or set the GitHub Actions repository variable `ALLOW_DISABLE_AUTO_SHUTDOWN=true`:

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

### Teardown Delay Limits

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

What a user sees with the policy in place is described under [Scheduled Teardown](../user-guides/settings.md#scheduled-teardown) in the Settings guide.

## Hetzner Object Storage for LakeFS

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

## Email Notifications via Resend

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

## Docker Hub Credentials

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

## Website Documentation Sync

Documentation in `docs/` can be synced to [nexus-stack.ch](https://nexus-stack.ch) when changes are pushed to `main`. This is handled by the `sync-docs-site.yml` workflow and only runs on the original repository (not on forks).

See [Website Sync Guide](docs-website-sync.md) for setup instructions. Sync requires a Cloudflare Deploy Hook URL stored as `WEBSITE_DEPLOY_HOOK` secret and the `WEBSITE_SYNC_ENABLED` repository variable set to `true`.
