# Control Plane

Web-based control plane to manage Nexus-Stack infrastructure via GitHub Actions.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  Cloudflare Pages (control.domain.com)         │
│  ┌──────────────┐     ┌──────────────────────┐ │
│  │   Frontend   │────▶│  Pages Functions     │ │
│  │  index.html  │     │  /api/spin-up        │ │
│  └──────────────┘     │  /api/teardown       │ │
│                       │  /api/services       │ │
│                       │  /api/status         │ │
│                       └──────────────────────┘ │
│                              │                  │
│                              │ GITHUB_TOKEN     │
│                              ▼                  │
│                       GitHub Actions API        │
└─────────────────────────────────────────────────┘
```

**No build step required** - pure HTML + JavaScript + Pages Functions.

## 🚀 Features

- **Spin Up** - Re-create infrastructure after teardown
- **Teardown** - Stop infrastructure (keeps control plane + R2 state)
- **Services** - Enable/disable services and trigger spin-up
- **Status** - Real-time workflow monitoring
- **Secure** - GitHub token stays server-side, protected by Cloudflare Access

## 📁 Structure

```
control-plane/
├── pages/
│   ├── index.html              # Frontend UI
│   ├── nexus-logo-green.png   # Logo
│   └── functions/              # Cloudflare Pages Functions (API)
│       └── api/
│           ├── spin-up.js      # POST /api/spin-up
│           ├── teardown.js     # POST /api/teardown
│           ├── services.js     # GET/POST /api/services
│           ├── status.js       # GET /api/status
│           ├── info.js         # GET /api/info
│           ├── debug.js        # GET /api/debug
│           ├── health.js       # GET /api/health
│           └── send-credentials.js  # POST /api/send-credentials
├── worker/
│   └── src/
│       └── index.js            # Scheduled teardown Worker (deployed via Terraform)
├── README.md                   # This file
├── SECURITY.md                 # Security documentation
└── DEPLOYMENT.md               # Deployment guide
```

## 🔍 Debug & Info Endpoints

The Control Plane provides endpoints for debugging and monitoring:

### GET /api/info
Returns infrastructure information including server details, uptime, and workflow history.

```bash
curl https://control.YOUR_DOMAIN/api/info
```

Response includes:
- `server`: type, location, domain
- `time`: lastDeploy, lastTeardown, uptime
- `scheduledTeardown`: enabled, timezone, nextTeardown
- `workflows`: lastDeploy, lastSpinUp, lastTeardown details

### GET /api/debug
Returns environment variable status for troubleshooting (values are masked).

```bash
curl https://control.YOUR_DOMAIN/api/debug
```

Response shows which environment variables are set or missing:
- `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`
- `DOMAIN`, `ADMIN_EMAIL`, `RESEND_API_KEY`
- `SERVER_TYPE`, `SERVER_LOCATION`

## 🔧 Setup

The control plane infrastructure is created by OpenTofu via GitHub Actions. The Pages deployment happens automatically during the `setup-control-plane` workflow.

### Required Secrets

Set these via **Cloudflare Dashboard** or **Wrangler CLI**:

#### Via Cloudflare Dashboard:
1. Go to **Cloudflare Dashboard** → **Pages** → **nexus-{domain}-control** (e.g., `nexus-stefanko-ch-control`)
2. **Settings** → **Environment Variables**
3. Add **Production** variables:
   - `GITHUB_OWNER` = `stefanko-ch` (auto-set by Terraform)
   - `GITHUB_REPO` = `Nexus-Stack` (auto-set by Terraform)
   - `GITHUB_TOKEN` = Your GitHub Personal Access Token (**Secret**)

#### Via Wrangler CLI:
```bash
cd control-plane/pages
# Replace {domain} with your domain (e.g., nexus-stefanko-ch-control)
npx wrangler pages secret put GITHUB_TOKEN --project-name=nexus-{domain}-control
```

### GitHub Token Requirements

Create a Personal Access Token with:
- **Classic:** `repo` (full control of private repositories)
- **Fine-grained:** `Actions: Write`, `Contents: Read`, `Contents: Write`

Generate at: https://github.com/settings/tokens

## 🌐 Access

Once deployed, visit:
```
https://control.YOUR_DOMAIN
```

Protected by **Cloudflare Access** - only admin email can access.

## 🔒 Security

- ✅ GitHub token is **never exposed** to the frontend
- ✅ All API calls run **server-side** (Cloudflare Edge)
- ✅ Protected by **Cloudflare Access** (email OTP)
- ✅ No CORS issues (frontend + API same origin)

## 📊 Workflow States

| State | Description |
|-------|-------------|
| **Deployed** | Infrastructure running, services accessible |
| **Torn Down** | Infrastructure stopped, control plane + R2 active |
| **Offline** | Everything deleted (first deployment) |
| **Running** | Workflow in progress, please wait |

## 🧪 Local Development

Pages Functions can be tested locally with Wrangler:

```bash
cd control-plane/pages
npx wrangler pages dev .
```

Access at `http://localhost:8788`

## 🐛 Troubleshooting

### "Failed to trigger workflow"
- Check `GITHUB_TOKEN` is set correctly
- Verify token has `workflow` scope or `Actions: Write`
- Check `GITHUB_OWNER` and `GITHUB_REPO` match your repository

### "Failed to fetch status"
- Same as above - token permissions issue

### "Failed to update services"
- Verify token has `Contents: Write`

### Workflows not appearing
- Wait a few seconds for GitHub API propagation
- Check workflows exist in `.github/workflows/`

## 📝 Deployment Flow

```bash
# Deploy via GitHub Actions
gh workflow run initial-setup.yaml    # First-time setup
gh workflow run spin-up.yml           # Re-deploy after teardown

# Set GitHub token secret
# → Via Cloudflare Dashboard (see above)
# → Or via Wrangler CLI

# Control plane is now live at https://control.YOUR_DOMAIN
```

## 🔄 Updates

When you update the control plane:

```bash
git add control-plane/
git commit -m "feat: Update control plane UI"
git push

# Cloudflare Pages auto-deploys on push
```

No manual deployment needed - Cloudflare Pages watches the `main` branch.

---

**Note:** The control plane **survives teardown** but is **destroyed** on `destroy-all`.
