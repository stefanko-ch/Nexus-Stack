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
   | Zone | DNS | Edit |
   | Zone | Zone | Read |

   > **Note:** The "Access: Organizations" permission is required for revoking Zero Trust sessions during `make down`. The "Access: Service Tokens" permission enables headless SSH authentication for CI/CD.

6. **Account Resources:** Include → All accounts (or specific)
7. **Zone Resources:** Include → Specific Zone → Your domain
8. Click **"Continue to summary"** → **"Create Token"**
9. **Copy the token!**

---

## 3️⃣ Configure Nexus

### Create Configuration File

```bash
cd tofu
cp config.tfvars.example config.tfvars
```

### Edit config.tfvars

```hcl
# Hetzner Cloud
hcloud_token = "YOUR_HCLOUD_TOKEN"

# Cloudflare
cloudflare_api_token  = "YOUR_CLOUDFLARE_TOKEN"
cloudflare_account_id = "YOUR_ACCOUNT_ID"
cloudflare_zone_id    = "YOUR_ZONE_ID"

# Your domain
domain = "yourdomain.com"

# Your email (for Cloudflare Access login)
admin_email = "you@example.com"
```

---

## 4️⃣ Deploy

### Initialize and Apply

```bash
# From project root
make up
```

This will:
1. Initialize OpenTofu
2. Create the Hetzner server
3. Set up Cloudflare Tunnel
4. Configure DNS records
5. Deploy all Docker stacks

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

To destroy everything:

```bash
make down
```

> ⚠️ This deletes the server and all data!

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
