# 🚀 Nexus Setup Guide

This guide walks you through the complete setup of Nexus Stack.

---

## 📋 Prerequisites

### Accounts

- [ ] **Hetzner Cloud Account** — [Sign up](https://console.hetzner.cloud/)
- [ ] **Cloudflare Account** — [Sign up](https://dash.cloudflare.com/sign-up)
- [ ] **Domain on Cloudflare** — DNS must be managed by Cloudflare

### Local Tools

- [ ] **OpenTofu** ≥ 1.6 — `brew install opentofu`
- [ ] **cloudflared** CLI — `brew install cloudflared`
- [ ] **jq** — `brew install jq`
- [ ] **SSH Key** (Ed25519 recommended)

### Quick Install (macOS)

```bash
brew install opentofu cloudflared jq

# Create SSH key if you don't have one
ssh-keygen -t ed25519 -C "nexus"
```

---

## 1️⃣ Create Hetzner Project

> ⚠️ Projects can only be created manually — not via API/OpenTofu.

1. Go to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Click **"+ New Project"**
3. Name it `Nexus` (or whatever you prefer)
4. Open the project

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
   | Zone | DNS | Edit |
   | Zone | Zone | Read |

   > **Note:** 
   > - "Workers R2 Storage" is required for the remote state backend
   > - "Access: Organizations" is required for revoking Zero Trust sessions during `make down`
   > - "Access: Service Tokens" enables headless SSH authentication for CI/CD

6. **Account Resources:** Include → All accounts (or specific)
7. **Zone Resources:** Include → Specific Zone → Your domain
8. Click **"Continue to summary"** → **"Create Token"**
9. **Copy the token!**

---

## 3️⃣ Configure Nexus

Nexus-Stack uses **two config files** for security:

### Create Configuration Files

```bash
# From project root
make init

# Copy and edit secrets file
cp .env.example .env
nano .env
```

### Edit .env (Secrets - never commit!)

```bash
export TF_VAR_hcloud_token="YOUR_HCLOUD_TOKEN"
export TF_VAR_cloudflare_api_token="YOUR_CLOUDFLARE_TOKEN"
export TF_VAR_cloudflare_account_id="YOUR_ACCOUNT_ID"
```

### Edit tofu/config.tfvars (Settings)

```hcl
# Cloudflare Zone (non-sensitive)
cloudflare_zone_id = "YOUR_ZONE_ID"

# Your domain
domain = "yourdomain.com"

# Your email (for Cloudflare Access login)
admin_email = "you@example.com"
```

> 💡 **Why two files?** Secrets in `.env` can be set as GitHub Actions secrets for CI/CD, while `config.tfvars` can be safely committed.

---

## 4️⃣ Deploy

### Initialize

```bash
# First time: create R2 bucket for remote state
source .env && make init
```

### Apply

```bash
# Deploy everything
source .env && make up
```

This will:
1. Create R2 bucket for remote state (first run only)
2. Initialize OpenTofu with remote backend
3. Create the Hetzner server
4. Set up Cloudflare Tunnel
5. Configure DNS records
6. Deploy all Docker stacks

### First deployment takes ~5 minutes

The server needs to:
- Boot up
- Run cloud-init (install Docker, cloudflared)
- Start all containers

---

## 5️⃣ Access Your Services

After deployment, your services are available at:

| Service | URL |
|---------|-----|
| Dashboard | `https://info.yourdomain.com` |
| Grafana | `https://grafana.yourdomain.com` |
| Vault | `https://vault.yourdomain.com` |
| Status | `https://status.yourdomain.com` |
| Portainer | `https://portainer.yourdomain.com` |
| IT-Tools | `https://it-tools.yourdomain.com` |

### First Login

1. Open any service URL
2. Cloudflare Access will prompt for your email
3. Enter the email you configured in `admin_email`
4. Check your inbox for the verification code
5. Enter the code — you're in!

### View Passwords

```bash
make secrets
```

---

## 6️⃣ SSH Access

SSH also goes through Cloudflare Tunnel. The deploy script automatically configures your SSH:

```bash
# Simply run:
ssh nexus
```

### Service Token (Automatic)

Nexus-Stack automatically creates a Cloudflare Service Token that enables SSH without browser login. This is configured automatically during `make up`.

Benefits:
- **No browser popup** — SSH works immediately
- **CI/CD ready** — Perfect for automated workflows
- **Persistent** — No re-authentication needed

The SSH config uses the Service Token:
```
Host nexus
  HostName ssh.yourdomain.com
  User root
  ProxyCommand bash -c 'TUNNEL_SERVICE_TOKEN_ID=xxx TUNNEL_SERVICE_TOKEN_SECRET=xxx cloudflared access ssh --hostname %h'
```

### Manual Login (Fallback)

If the Service Token is not available, authenticate via browser:

```bash
cloudflared access login https://ssh.yourdomain.com
```

---

## 🧹 Teardown

### Destroy Infrastructure (keep state)

```bash
# Local
make down

# Or via GitHub Actions (no confirmation needed)
gh workflow run down.yml
```

> This deletes the server but keeps the R2 state bucket for future deployments.

### Full Cleanup (delete everything)

```bash
# Local
make destroy

# Or via GitHub Actions (requires "DESTROY" confirmation)
gh workflow run destroy.yml -f confirm=DESTROY
```

> ⚠️ This deletes everything: server, R2 bucket, API tokens, local credentials.

---

## 🤖 GitHub Actions Deployment

You can deploy entirely via GitHub Actions - no local tools required!

### Initial GitHub Secrets (before first deploy)

Add these secrets to your repo:

**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Source | Description |
|-------------|--------|-------------|
| `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard | API access |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard | Account ID |
| `CLOUDFLARE_ZONE_ID` | Cloudflare dashboard | Zone ID |
| `HCLOUD_TOKEN` | Hetzner console | API token |
| `DOMAIN` | Your domain | e.g. `example.com` |
| `ACCESS_EMAILS` | Allowed emails | Comma-separated |
| `INFISICAL_TOKEN` | Infisical dashboard | Optional |

### First Deployment

```bash
# Run the deploy workflow
gh workflow run deploy.yml
```

On **first run**, the pipeline will:
1. Create the R2 bucket automatically
2. Generate R2 API credentials
3. **Display the credentials in the logs** with instructions
4. Deploy the infrastructure

> ⚠️ **Important:** After the first run, copy the `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` from the logs and save them as GitHub Secrets!

### Add R2 Credentials as Secrets

After the first deploy, add these two additional secrets:

| Secret Name | Source |
|-------------|--------|
| `R2_ACCESS_KEY_ID` | Shown in first deploy logs |
| `R2_SECRET_ACCESS_KEY` | Shown in first deploy logs |

Once saved, all future deployments will use these secrets automatically.

### Available Workflows

| Workflow | Command | Confirmation | Description |
|----------|---------|--------------|-------------|
| Deploy | `gh workflow run deploy.yml` | None | Full deploy |
| Stop | `gh workflow run down.yml` | None | Stop infra (reversible) |
| Destroy | `gh workflow run destroy.yml -f confirm=DESTROY` | Required | Delete everything |

### Scheduled Deployment (Cost Saving)

Add a schedule trigger to automatically stop infrastructure at night:

```yaml
# In .github/workflows/down.yml, add to "on:" section:
on:
  workflow_dispatch:
  schedule:
    - cron: '0 22 * * *'  # Every day at 22:00 UTC
```

### Local + CI Coexistence

Both local and CI deployments share the same remote state in R2:
- ✅ Deploy locally, destroy via CI
- ✅ Deploy via CI, SSH locally  
- ✅ Multiple team members with same state

---

## 🔧 Troubleshooting

### "Cloud-init timeout"

The server is still booting. Wait a few minutes and try again:

```bash
make deploy --skip-wait
```

### "Tunnel not connecting"

Check if cloudflared is running on the server:

```bash
ssh nexus
systemctl status cloudflared
```

### "Permission denied"

Make sure your email matches `admin_email` in nexus.tfvars.

---

## 📚 Next Steps

- Add more stacks by editing `nexus.tfvars`
- Check Grafana for logs and metrics
- Set up alerts in Uptime Kuma
- Store secrets in Vault
