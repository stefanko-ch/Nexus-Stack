# Control Plane User Guide

The Control Plane is your web interface for managing Nexus-Stack infrastructure. Access it at:

```
https://control.YOUR_DOMAIN
```

> Protected by Cloudflare Access - you'll need to verify your email on first access.

---

## Dashboard Overview

The Control Plane shows:
- **Current Status** - Whether infrastructure is deployed, torn down, or in progress
- **Version** - Current Nexus-Stack release (click refresh to update)
- **Action Buttons** - Control your infrastructure

---

## Actions

### ⚡ Spin Up

Deploys the Hetzner server and all enabled services.

**When to use:**
- After a teardown to bring services back online
- First deployment after initial setup

**What happens:**
1. Creates Hetzner Cloud server
2. Sets up Cloudflare Tunnel
3. Deploys Docker containers
4. Configures DNS and Access policies
5. Sends "Stack Online" email

### 💤 Teardown

Stops infrastructure to save costs. Your data and configuration are preserved.

**What's kept:**
- Control Plane (always available)
- OpenTofu state in Cloudflare R2
- All configuration

**What's removed:**
- Hetzner server (and associated costs)
- Docker containers
- Cloudflare Tunnel

**Tip:** Use scheduled teardown for automatic daily shutdown.

### 🗑️ Destroy All

Completely removes all infrastructure including state. **This is irreversible.**

Requires typing `DESTROY` to confirm.

---

## Services Management

Click **Services** to manage which stacks are deployed.

### Enable/Disable Services

Toggle services on or off. Changes are saved to `tofu/services.tfvars` in the repository.

### Deploy Changes

After changing services, click **Deploy with Changes** to apply. This triggers a Spin Up workflow with the updated configuration.

### Available Services

| Service | Description |
|---------|-------------|
| IT-Tools | Developer utilities |
| Excalidraw | Whiteboard for diagrams |
| Portainer | Docker management |
| Uptime Kuma | Monitoring |
| Infisical | Secrets management |
| Grafana | Observability stack |
| Kestra | Workflow orchestration |
| n8n | Automation |
| Mailpit | Email testing |

---

## Scheduled Teardown

Automatically tear down infrastructure daily to save costs.

### Enable via UI

1. Click **Scheduled Teardown** in the Control Plane
2. Toggle **Enable scheduled teardown**
3. Configure time and timezone
4. Click **Save**

### Enable via API

```bash
# Enable with default settings (22:00 Europe/Zurich)
curl -X POST https://control.YOUR_DOMAIN/api/scheduled-teardown \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Custom time
curl -X POST https://control.YOUR_DOMAIN/api/scheduled-teardown \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "timezone": "Europe/Zurich", "teardownTime": "23:00"}'

# Check current settings
curl https://control.YOUR_DOMAIN/api/scheduled-teardown
```

### How It Works

1. **21:45** - Email notification sent (15 min warning)
2. **22:00** - Teardown workflow triggered

Times are configurable. Notification is always 15 minutes before teardown.

---

## Credentials Email

Click **Send Credentials** to receive an email with all service passwords.

The email includes:
- Admin usernames and passwords for each service
- Direct links to service URLs
- SSH access instructions

---

## Status Indicators

| Status | Meaning |
|--------|---------|
| 🟢 **Deployed** | Infrastructure is running |
| 🔴 **Torn Down** | Infrastructure is stopped |
| 🟡 **In Progress** | Workflow is running |
| ⚪ **Unknown** | Unable to determine status |

Click **Refresh** to update the status.

---

## Troubleshooting

### "Unknown" Status

The status API checks GitHub Actions workflow runs. If you see "Unknown":
- Refresh the page
- Check if GitHub token has correct permissions
- View GitHub Actions directly for workflow status

### Spin Up Fails

Common causes:
- Hetzner API token expired
- Cloudflare API token missing permissions
- R2 credentials not set

Check the GitHub Actions workflow logs for details.

### Can't Access Control Plane

The Control Plane runs on Cloudflare Pages and should always be available, even after teardown.

If inaccessible:
1. Check Cloudflare Pages status
2. Verify DNS record exists for `control.YOUR_DOMAIN`
3. Check Cloudflare Access policy

---

## Technical Details

### Architecture

- **Frontend**: Static HTML served by Cloudflare Pages
- **API**: Cloudflare Pages Functions (serverless)
- **Storage**: Cloudflare D1 for configuration, Cloudflare Secrets for credentials
- **Workflows**: Triggered via GitHub Actions API

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Current infrastructure status |
| `/api/spin-up` | POST | Trigger spin-up workflow |
| `/api/teardown` | POST | Trigger teardown workflow |
| `/api/destroy` | POST | Trigger destroy-all workflow |
| `/api/services` | GET | List all services |
| `/api/services` | POST | Update service configuration |
| `/api/scheduled-teardown` | GET/POST | Scheduled teardown config |
| `/api/info` | POST | Send credentials email |
| `/api/version` | GET | Get current release version |

### Required Secrets

The Control Plane needs these environment variables (set in Cloudflare Pages):

| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | Trigger GitHub Actions workflows |
| `GITHUB_OWNER` | Repository owner |
| `GITHUB_REPO` | Repository name |
| `RESEND_API_KEY` | Send emails (optional) |
| `ADMIN_EMAIL` | Email recipient |
| `DOMAIN` | Your domain |

---

## See Also

- [Setup Guide](setup-guide.md) - Initial setup instructions
- [Stacks Documentation](stacks.md) - Detailed stack information
- [control-panel/README.md](../control-panel/README.md) - Developer documentation
