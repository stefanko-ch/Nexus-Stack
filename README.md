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

🚀 **One-command deployment: Hetzner server + Cloudflare Tunnel + Docker - fully automated.**

> ⚠️ **Disclaimer:** This project was developed and tested on macOS. Use at your own risk. While care has been taken to ensure security, you are responsible for reviewing the code and understanding what it does before running it.

## What This Does

- Creates a Hetzner Cloud server
- Sets up Cloudflare Tunnel with Zero Trust authentication
- Deploys your Docker services behind Cloudflare Access
- Everything accessible only to your email address
- SSH via Cloudflare Tunnel - **zero open ports**

**Zero Entry** = Zero open ports = Zero attack surface

## Prerequisites

- **[OpenTofu](https://opentofu.org/docs/intro/install/)** - Infrastructure as Code tool (macOS: `brew install opentofu`)
- **[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)** - Required locally for SSH proxy through Cloudflare Tunnel (macOS: `brew install cloudflared`)
- **[Hetzner Cloud](https://console.hetzner.cloud/) account** - For the server
- **[Cloudflare](https://cloudflare.com) account** - Free tier is sufficient
- **A domain** - Can be purchased from any registrar, but must be [added to Cloudflare](https://developers.cloudflare.com/fundamentals/setup/manage-domains/add-site/) (Cloudflare manages DNS)
- **SSH key pair** - Must exist at `~/.ssh/id_ed25519`. Generate with: `ssh-keygen -t ed25519`

## Quick Start

```bash
# 1. Clone this repo
git clone https://github.com/stefanko-ch/Nexus-Stack.git
cd Nexus-Stack

# 2. Create config files
make init

# 3. Add your secrets to .env
cp .env.example .env
nano .env

# 4. Edit domain/email settings
nano tofu/config.tfvars

# 5. Deploy everything
source .env && make up
```

That's it! After a few minutes you'll have:
- `https://it-tools.yourdomain.com` - IT-Tools (protected by Cloudflare Access)
- `ssh nexus` - SSH access via Cloudflare Tunnel

## Configuration

Nexus-Stack uses **two config files** for security:

### 1. `.env` - Secrets (never committed)

```bash
export TF_VAR_hcloud_token="xxx"
export TF_VAR_cloudflare_api_token="xxx"
export TF_VAR_cloudflare_account_id="xxx"
```

| Variable | Where to get it |
|----------|-----------------|
| `TF_VAR_hcloud_token` | [Hetzner Console](https://console.hetzner.cloud/) → Project → Security → API Tokens |
| `TF_VAR_cloudflare_api_token` | [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token |
| `TF_VAR_cloudflare_account_id` | URL when logged into Cloudflare: `dash.cloudflare.com/<account_id>/...` |

### 2. `tofu/config.tfvars` - Settings (can be committed)

| Setting | Description |
|---------|-------------|
| `cloudflare_zone_id` | Domain overview page → right sidebar |
| `domain` | Your domain in Cloudflare |
| `admin_email` | Your email for authentication |
| `services` | Which stacks to deploy |

### Cloudflare API Token Permissions

Create a Custom Token with these permissions:
- Zone:DNS:Edit
- Zone:Zone:Read
- Account:Cloudflare Tunnel:Edit
- Account:Access: Apps and Policies:Edit
- Account:Access: Service Tokens:Edit
- Account:Access: Organizations:Edit
- **Account:Workers R2 Storage:Edit** ← Required for remote state

See [docs/setup-guide.md](docs/setup-guide.md#create-api-token) for details.

### Docker Hub Login (Optional)

Docker Hub limits anonymous pulls to 100 per 6 hours per IP. During development with frequent `make down` / `make up` cycles, this limit is quickly reached since each deployment pulls multiple images (Grafana stack alone requires 6 images).

To avoid rate limits, add your Docker Hub credentials:

```hcl
dockerhub_username = "your-username"
dockerhub_token    = "dckr_pat_xxxx"  # Create at hub.docker.com/settings/security
```

This doubles your limit to 200 pulls/6h with a free account.

## Available Stacks

![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)
![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)
![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)
![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)
![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)
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
| **Info** | Landing page with service overview dashboard | — |

All stacks are pre-configured and ready to deploy. Just enable them in `config.tfvars`.

→ See [docs/stacks.md](docs/stacks.md) for detailed stack documentation.

## Commands

All commands (except `make init`) require environment variables:
```bash
source .env && make <command>
```

| Command | Description |
|---------|-------------|
| `make init` | First-time setup - creates config files and R2 bucket |
| `make up` | Create infrastructure + deploy containers |
| `make down` | Destroy infrastructure (keeps R2 state) |
| `make destroy` | Full cleanup: infrastructure + R2 bucket + credentials |
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
│   ├── main.tf           # Server, tunnel, DNS, access
│   ├── variables.tf      # Input variables
│   ├── outputs.tf        # Outputs (IPs, URLs)
│   ├── providers.tf      # Provider config + R2 backend
│   ├── config.tfvars.example  # Template for settings
│   └── config.tfvars     # Your settings (git-ignored)
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
- **Persistent authentication** - Token doesn't expire

The SSH config is automatically configured with the Service Token:
```
Host nexus
  HostName ssh.yourdomain.com
  User root
  ProxyCommand bash -c 'TUNNEL_SERVICE_TOKEN_ID=xxx TUNNEL_SERVICE_TOKEN_SECRET=xxx cloudflared access ssh --hostname %h'
```

> ℹ️ **Note:** The Service Token is stored in the OpenTofu state. After `make down`, you'll need to run `make up` again to get a new token.

### Manual Browser Login (Fallback)

If the Service Token is not available (e.g., first deployment before infrastructure exists), the script falls back to browser-based authentication:

```bash
# Manual authentication if needed:
cloudflared access login https://ssh.yourdomain.com
```

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