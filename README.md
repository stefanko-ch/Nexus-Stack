# Nexus-Stack

![Nexus-Stack](docs/images/Nexus-Logo-BlackWhite.png)

![GitHub License](https://img.shields.io/github/license/stefanko-ch/Nexus-Stack)
![GitHub issues](https://img.shields.io/github/issues/stefanko-ch/Nexus-Stack)
![GitHub pull requests](https://img.shields.io/github/issues-pr/stefanko-ch/Nexus-Stack)
![GitHub last commit](https://img.shields.io/github/last-commit/stefanko-ch/Nexus-Stack)

![OpenTofu](https://img.shields.io/badge/OpenTofu-FFDA18?logo=opentofu&logoColor=black)
![Hetzner](https://img.shields.io/badge/Hetzner-D50C2D?logo=hetzner&logoColor=white)
![Cloudflare](https://img.shields.io/badge/Cloudflare-F38020?logo=cloudflare&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white)
![Resend](https://img.shields.io/badge/Resend-000000?logo=resend&logoColor=white)

🚀 **One-command deployment: Hetzner server + Cloudflare Tunnel + Docker - fully automated.**

> ⚠️ **Disclaimer:** Use at your own risk. While care has been taken to ensure security, you are responsible for reviewing the code and understanding what it does before running it.

## What This Does

### Infrastructure
- **Hetzner Cloud Server** - ARM-based (cax11/cax31) running Ubuntu 24.04
- **Cloudflare Tunnel** - All traffic routed through Cloudflare, zero open ports
- **Cloudflare Access** - Email OTP authentication for all services
- **Remote State** - OpenTofu state stored in Cloudflare R2

### Automation
- **Control Plane** - Web UI to manage infrastructure (spin up, teardown, services)
- **GitHub Actions** - Full CI/CD deployment without local tools
- **Scheduled Teardown** - Optional daily auto-shutdown to save costs
- **Email Notifications** - Credentials and status emails via Resend

### Security
- **Zero Entry** - Zero open ports = Zero attack surface
- **Service Tokens** - Headless SSH access for CI/CD
- **Secrets Management** - Centralized in Infisical with auto-provisioning

### Developer Experience
- **One-Command Deploy** - `make up` deploys everything
- **Modular Stacks** - Enable/disable services via config
- **Auto-Setup** - Admin users created automatically with generated passwords
- **Info Page** - Dashboard with all service URLs and credentials

## Prerequisites

- **[OpenTofu](https://opentofu.org/docs/intro/install/)** - Infrastructure as Code tool (macOS: `brew install opentofu`)
- **[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)** - Required locally for SSH proxy through Cloudflare Tunnel (macOS: `brew install cloudflared`)
- **[Hetzner Cloud](https://console.hetzner.cloud/) account** - For the server
- **[Cloudflare](https://cloudflare.com) account** - Free tier is sufficient
- **A domain** - Can be purchased from any registrar, but must be [added to Cloudflare](https://developers.cloudflare.com/fundamentals/setup/manage-domains/add-site/) (Cloudflare manages DNS)
- **SSH key pair** - Must exist at `~/.ssh/id_ed25519`. Generate with: `ssh-keygen -t ed25519`

## Getting Started

For complete installation and configuration instructions, see the **[Setup Guide](docs/setup-guide.md)**.

**Quick Overview:**
1. Clone the repo and run `make init`
2. Configure `.env` with API tokens and `tofu/stack/config.tfvars` with settings
3. Run `source .env && make up`

After deployment you'll have:
- `https://control.yourdomain.com` - Control Plane to manage infrastructure
- `https://info.yourdomain.com` - Service dashboard with credentials
- `ssh nexus` - SSH access via Cloudflare Tunnel

## Available Stacks

![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)
![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)
![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)
![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)
![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)
![Mailpit](https://img.shields.io/badge/Mailpit-F36F21?logo=maildotru&logoColor=white)
![Info](https://img.shields.io/badge/Info-00D4AA?logo=nginx&logoColor=white)

| Stack | Description | Website |
|-------|-------------|--------|
| **IT-Tools** | Collection of handy online tools for developers | [it-tools.tech](https://it-tools.tech) |
| **Excalidraw** | Virtual whiteboard for sketching hand-drawn diagrams | [excalidraw.com](https://excalidraw.com) |
| **Portainer** | Docker container management UI | [portainer.io](https://www.portainer.io) |
| **Uptime Kuma** | A fancy self-hosted monitoring tool | [uptime.kuma.pet](https://uptime.kuma.pet) |
| **Infisical** | Open-source secret management platform | [infisical.com](https://infisical.com) |
| **Grafana** | Full observability stack with Prometheus, Loki & dashboards | [grafana.com](https://grafana.com) |
| **Kestra** | Modern workflow orchestration for data pipelines & automation | [kestra.io](https://kestra.io) |
| **n8n** | Workflow automation tool - automate anything | [n8n.io](https://n8n.io) |
| **Mailpit** | Email & SMTP testing tool - catch and inspect emails | [mailpit.axllent.org](https://mailpit.axllent.org) |
| **Info** | Landing page with service overview dashboard | — |

All stacks are pre-configured and ready to deploy. Just enable them in `config.tfvars`.

→ See [docs/stacks.md](docs/stacks.md) for detailed stack documentation.

## Control Plane

Manage your Nexus-Stack infrastructure via web interface at `https://control.YOUR_DOMAIN`.

**Features:**
- ⚡ **Spin Up / Teardown** - Start and stop infrastructure with one click
- 🧩 **Services** - Enable/disable services dynamically
- ⏰ **Scheduled Teardown** - Auto-shutdown to save costs
- 📧 **Credentials Email** - Send login credentials to your inbox

→ See [docs/control-plane.md](docs/control-plane.md) for the user guide.

## Commands

All commands (except `make init`) require environment variables:
```bash
source .env && make <command>
```

| Command | Description |
|---------|-------------|
| `make init` | First-time setup - creates config files and R2 bucket |
| `make up` | Create infrastructure + deploy containers |
| `make teardown` | Teardown infrastructure (keeps R2 state for re-deploy) |
| `make destroy-all` | Full cleanup: infrastructure + R2 bucket + credentials |
| `make status` | Show running containers |
| `make ssh` | SSH into the server |
| `make logs` | View container logs (default: it-tools) |
| `make logs SERVICE=excalidraw` | View logs for specific service |
| `make plan` | Preview changes |
| `make urls` | Show all service URLs |
| `make secrets` | Show service admin passwords |

## Adding More Services

Adding a new service only requires **2 steps**:

### 1. Create the Docker Compose stack

```bash
mkdir -p stacks/my-app
```

Create `stacks/my-app/docker-compose.yml`:
```yaml
services:
  my-app:
    image: my-app-image:latest
    container_name: my-app
    restart: unless-stopped
    ports:
      - "8090:80"  # Pick an unused port
    networks:
      - app-network

networks:
  app-network:
    external: true
```

### 2. Add to config.tfvars

```hcl
services = {
  # ... existing services ...
  
  my-app = {
    enabled   = true
    subdomain = "my-app"    # → https://my-app.yourdomain.com
    port      = 8090        # Must match docker-compose port
    public    = false       # false = requires login, true = public
  }
}
```

### 3. Deploy

```bash
make up
```

That's it! OpenTofu automatically creates:
- ✅ DNS record
- ✅ Tunnel ingress route
- ✅ Cloudflare Access application
- ✅ Access policy (email-based auth)

## Disabling Services

To disable a service, set `enabled = false` in `config.tfvars`:

```hcl
services = {
  it-tools = {
    enabled   = true
    # ...
  }
  
  excalidraw = {
    enabled   = false    # ← Disabled
    subdomain = "draw"
    port      = 8082
    public    = false
  }
}
```

Then run `make up`. This will:
1. **Remove** the DNS record from Cloudflare
2. **Remove** the tunnel ingress route
3. **Remove** the Cloudflare Access application and policy
4. **Stop** the Docker container on the server
5. **Delete** the stack folder from the server

The service is completely cleaned up - no orphaned resources.

## File Structure

```
Nexus-Stack/
├── Makefile              # Main commands
├── .env.example          # Template for secrets (TF_VAR_*)
├── .env                  # Your secrets (git-ignored)
├── tofu/                 # Infrastructure as Code
│   ├── backend.hcl       # R2 backend configuration
│   ├── services.tfvars   # Service definitions
│   ├── config.tfvars.example  # Template for settings
│   ├── stack/            # Server, tunnel, services
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── providers.tf
│   │   └── config.tfvars # Your settings (git-ignored)
│   └── control-plane/    # Control Plane (Cloudflare Pages)
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── providers.tf
├── stacks/               # Docker Compose stacks
│   ├── it-tools/         # Example: IT-Tools
│   └── excalidraw/       # Example: Excalidraw
└── scripts/
    ├── init-r2-state.sh   # Creates R2 bucket for state
    └── deploy.sh         # Container deployment
```

## SSH Access

The deploy script automatically configures SSH. Just run:

```bash
ssh nexus
```

### Service Token Authentication (Headless)

Nexus-Stack automatically creates a Cloudflare Service Token for SSH access. This enables:
- **No browser login required** - SSH works immediately without email verification
- **CI/CD ready** - Perfect for automated deployments with GitHub Actions

## GitHub Actions Deployment

Deploy entirely via CI - no local tools required!

| Workflow | Description |
|----------|-------------|
| **Initial Setup** | One-time setup (Control Plane + Spin Up) |
| **Spin Up** | Re-create infrastructure after teardown |
| **Teardown** | Teardown infrastructure (keeps state) |
| **Destroy All** | Delete everything |

```bash
# First time setup
gh workflow run initial-setup.yaml

# Daily operations via Control Plane UI
# Or via CLI:
gh workflow run spin-up.yml
gh workflow run teardown.yml
```

→ See [docs/setup-guide.md](docs/setup-guide.md#-github-actions-deployment) for configuration details.

## Security

This setup achieves **zero open ports** after deployment:

1. During initial setup, SSH (port 22) is temporarily open
2. OpenTofu installs the Cloudflare Tunnel via SSH
3. After tunnel is running, SSH port is **automatically closed** via Hetzner API

4. All future SSH access goes through Cloudflare Tunnel

**Result:** No attack surface. All traffic flows through Cloudflare.

- Services are protected by Cloudflare Access (email OTP)
- Set `public = true` in config if you want a service publicly accessible

## Troubleshooting

```bash
# SSH not working? Re-authenticate:
cloudflared access login https://ssh.yourdomain.com

# Check containers:
make ssh
docker ps -a

# Check tunnel status:
systemctl status cloudflared
journalctl -u cloudflared -f

# View service logs:
make logs SERVICE=it-tools
```

## License

[MIT](LICENSE)