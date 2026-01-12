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

# 2. Initialize and create config
make init

# 3. Edit config with your API tokens and services
nano tofu/config.tfvars

# 4. Deploy everything
make up
```

That's it! After ~5 minutes you'll have:
- `https://it-tools.yourdomain.com` - IT-Tools (protected by Cloudflare Access)
- `ssh nexus` - SSH access via Cloudflare Tunnel

## Configuration

Edit `tofu/config.tfvars`:

| Setting | Where to get it |
|---------|-----------------|
| `hcloud_token` | [Hetzner Console](https://console.hetzner.cloud/) → Project → Security → API Tokens |
| `cloudflare_api_token` | [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token |
| `cloudflare_account_id` | URL when logged into Cloudflare: `dash.cloudflare.com/<account_id>/...` |
| `cloudflare_zone_id` | Domain overview page → right sidebar |
| `domain` | Your domain in Cloudflare |
| `admin_email` | Your email for authentication |

### Cloudflare API Token Permissions

Create a Custom Token. See [docs/setup-guide.md](docs/setup-guide.md#create-api-token) for the complete list of required permissions.

## Available Stacks

![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)
![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)
![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)
![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)
![Info](https://img.shields.io/badge/Info-00D4AA?logo=nginx&logoColor=white)

| Stack | Description | Website |
|-------|-------------|--------|
| **IT-Tools** | Collection of handy online tools for developers | [it-tools.tech](https://it-tools.tech) |
| **Excalidraw** | Virtual whiteboard for sketching hand-drawn diagrams | [excalidraw.com](https://excalidraw.com) |
| **Portainer** | Docker container management UI | [portainer.io](https://www.portainer.io) |
| **Uptime Kuma** | A fancy self-hosted monitoring tool | [uptime.kuma.pet](https://uptime.kuma.pet) |
| **Infisical** | Open-source secret management platform | [infisical.com](https://infisical.com) |
| **Info** | Landing page with service overview dashboard | — |

All stacks are pre-configured and ready to deploy. Just enable them in `config.tfvars`.

→ See [docs/stacks.md](docs/stacks.md) for detailed stack documentation.

## Commands

| Command | Description |
|---------|-------------|
| `make init` | First-time setup - creates config file |
| `make up` | Create infrastructure + deploy containers |
| `make down` | Destroy everything |
| `make status` | Show running containers |
| `make ssh` | SSH into the server |
| `make logs` | View container logs (default: it-tools) |
| `make logs SERVICE=excalidraw` | View logs for specific service |
| `make plan` | Preview changes |
| `make urls` | Show all service URLs |

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
├── tofu/                 # Infrastructure as Code
│   ├── main.tf           # Server, tunnel, DNS, access
│   ├── variables.tf      # Input variables
│   ├── outputs.tf        # Outputs (IPs, URLs)
│   ├── providers.tf      # Provider config
│   └── config.tfvars     # Your config (git-ignored)
├── stacks/               # Docker Compose stacks
│   ├── it-tools/         # Example: IT-Tools
│   └── excalidraw/       # Example: Excalidraw
└── scripts/
    └── deploy.sh         # Container deployment
```

## SSH Access

The deploy script automatically configures SSH. Just run:

```bash
ssh nexus
```

The config is added to `~/.ssh/config`:
```
Host nexus
  HostName ssh.yourdomain.com
  User root
  ProxyCommand cloudflared access ssh --hostname %h
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