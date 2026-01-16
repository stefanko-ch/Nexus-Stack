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
   | Account | Workers KV Storage | Edit |
   | Account | Workers Scripts | Edit |
   | Account | Cloudflare Pages | Edit |
   | Zone | DNS | Edit |
   | Zone | Zone | Read |

   > **Note:** 
   > - "Workers R2 Storage" is required for the remote state backend
   > - "Workers KV Storage" is required for KV namespaces used by the scheduler
   > - "Workers Scripts" is required for the scheduled teardown worker
   > - "Cloudflare Pages" is required for the Control Plane
   > - "Access: Organizations" is required for revoking Zero Trust sessions during `make teardown`
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

### Edit tofu/stack/config.tfvars (Settings)

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

### Teardown Infrastructure (keep state)

```bash
# Local
make teardown

# Or via GitHub Actions (no confirmation needed)
gh workflow run teardown.yml
```

> This deletes the server but keeps the R2 state bucket for future deployments.

### Full Cleanup (delete everything)

```bash
# Local
make destroy-all

# Or via GitHub Actions (requires "DESTROY" confirmation)
gh workflow run destroy-all.yml -f confirm=DESTROY
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
| `ADMIN_EMAIL` | Your email | For Cloudflare Access login |
| `ACCESS_EMAILS` | Allowed emails | Comma-separated |
| `INFISICAL_TOKEN` | Infisical dashboard | Optional |

### First Setup

```bash
# Run the initial setup workflow
gh workflow run initial-setup.yaml
```

On **first run**, the pipeline will:
1. Create the R2 bucket automatically
2. Generate R2 API credentials
3. Deploy the Control Plane
4. Trigger the spin-up workflow

> ⚠️ **Important:** After the first run, copy the `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` from the logs and save them as GitHub Secrets (unless `GH_SECRETS_TOKEN` is configured for auto-save).

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
| Initial Setup | `gh workflow run initial-setup.yaml` | None | One-time setup (Control Plane + Spin Up) |
| Setup Control Plane | `gh workflow run setup-control-plane.yaml` | None | Setup Control Plane only |
| Spin Up | `gh workflow run spin-up.yml` | None | Re-create infrastructure after teardown |
| Teardown | `gh workflow run teardown.yml` | None | Teardown infra (reversible) |
| Destroy All | `gh workflow run destroy-all.yml -f confirm=DESTROY` | Required | Delete everything |

### Scheduled Teardown (Cost Saving)

Scheduled teardown is optional and managed via the Control Plane (Cloudflare Worker + KV).
Enable or disable it at runtime without changing GitHub Actions.

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

---

## 📧 Email Notifications via Resend (Optional)

After deployment, Nexus-Stack can automatically send you an email with all service credentials. This requires Resend setup.

### Why Resend?

- **Free tier**: 3,000 emails/month, 100 emails/day
- **Domain verification**: Send from `nexus@yourdomain.com`
- **Simple API**: Easy integration with GitHub Actions
- **No SMTP server needed**: Direct API integration

### Setup Steps

#### 1. Create Resend Account

1. Go to [resend.com](https://resend.com)
2. Sign up (free account)
3. Verify your email address

#### 2. Add Your Domain

1. In Resend Dashboard → **Domains** → **Add Domain**
2. Enter your domain (e.g., `nexus-stack.ch`)
3. Click **Add Domain**

#### 3. Verify Domain (DNS Records)

Resend will show you DNS records to add. Add these in **Cloudflare DNS**:

**SPF Record (TXT):**
```
Type: TXT
Name: @ (or your domain)
Content: v=spf1 include:resend.com ~all
TTL: Auto
```

**DKIM Record (TXT):**
```
Type: TXT
Name: resend._domainkey (or similar)
Content: [provided by Resend]
TTL: Auto
```

**DMARC Record (TXT) - Optional but recommended:**
```
Type: TXT
Name: _dmarc
Content: v=DMARC1; p=none; rua=mailto:admin@yourdomain.com
TTL: Auto
```

**Steps in Cloudflare:**
1. Go to Cloudflare Dashboard → Your Domain → **DNS**
2. Click **Add record**
3. Add each record as shown above
4. Wait 5-10 minutes for DNS propagation

#### 4. Verify Domain in Resend

1. Go back to Resend Dashboard → **Domains**
2. Click **Verify** next to your domain
3. Wait for verification (usually 1-2 minutes)
4. Status should change to **Verified** ✅

#### 5. Create API Key

1. Resend Dashboard → **API Keys** → **Create API Key**
2. Name: `Nexus-Stack`
3. Permission: **Sending access**
4. Click **Create**
5. **Copy the API key** (starts with `re_` - you'll only see it once!)

#### 6. Add API Key to GitHub Secrets

```bash
gh secret set RESEND_API_KEY --body "re_xxxxxxxxxxxxx"
```

Or manually:
1. GitHub → Repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `RESEND_API_KEY`
4. Value: Your Resend API key
5. Click **Add secret**

### Test Email

After deployment, check your email (`ADMIN_EMAIL` secret) for:
- Subject: `🚀 Nexus-Stack Deployed - Your Credentials`
- Contains: Infisical admin password and service URLs

### Troubleshooting

**Email not received?**
- Check GitHub Actions logs for email step
- Verify `RESEND_API_KEY` secret is set correctly
- Check Resend Dashboard → **Logs** for delivery status
- Verify `ADMIN_EMAIL` secret matches your email

**Domain verification failed?**
- Double-check DNS records in Cloudflare
- Wait 10-15 minutes for DNS propagation
- Verify records match exactly what Resend shows
- Check Cloudflare DNS logs for any issues

**Using a different sender email?**
- Edit `.github/workflows/setup-control-plane.yaml` line 221
- Change `nexus@$DOMAIN` to your preferred email
- Must be from verified domain (e.g., `admin@yourdomain.com`)

---

## 🐳 Docker Hub Credentials (Optional)

Docker Hub limits anonymous image pulls to **100 pulls per 6 hours per IP**. During frequent deployments, this limit can be reached quickly since each stack requires multiple images.

### Benefits of Docker Hub Login

- **Without login**: 100 pulls/6h (anonymous)
- **With login**: 200 pulls/6h (free account)

### Setup for GitHub Actions

1. **Create Docker Hub Access Token:**
   - Go to https://hub.docker.com/settings/security
   - Click **"New Access Token"**
   - Name: `Nexus-Stack`
   - Permissions: **Read** (sufficient for pulls)
   - Click **Generate**
   - **Copy the token** (starts with `dckr_pat_`)

2. **Set GitHub Secrets:**
   ```bash
   gh secret set DOCKERHUB_USERNAME --body "your-dockerhub-username"
   gh secret set DOCKERHUB_TOKEN --body "dckr_pat_xxxxxxxxxxxxx"
   ```

3. **Verify:**
   ```bash
   gh secret list | grep DOCKERHUB
   ```

The deployment workflow will automatically use these credentials if set.

### Setup for Local Deployment

Add to your `.env` file:

```bash
export TF_VAR_dockerhub_username="your-dockerhub-username"
export TF_VAR_dockerhub_token="dckr_pat_xxxxxxxxxxxxx"
```

Or add to `tofu/stack/config.tfvars`:

```hcl
dockerhub_username = "your-dockerhub-username"
dockerhub_token    = "dckr_pat_xxxxxxxxxxxxx"
```

The `deploy.sh` script will automatically log in to Docker Hub during deployment if credentials are provided.
