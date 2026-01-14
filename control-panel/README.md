# Control Panel

Web-based control panel to manage Nexus-Stack infrastructure via GitHub Actions.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  Cloudflare Pages (control.domain.com)         │
│  ┌──────────────┐     ┌──────────────────────┐ │
│  │   Frontend   │────▶│  Pages Functions     │ │
│  │  index.html  │     │  /api/deploy         │ │
│  └──────────────┘     │  /api/teardown       │ │
│                       │  /api/destroy        │ │
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

- **Deploy** - Trigger full infrastructure deployment
- **Teardown** - Stop infrastructure (keeps control panel + R2 state)
- **Destroy** - Full cleanup (removes everything)
- **Status** - Real-time workflow monitoring
- **Secure** - GitHub token stays server-side, protected by Cloudflare Access

## 📁 Structure

```
control-panel/
├── pages/
│   ├── index.html              # Frontend UI
│   ├── nexus-logo-green.png   # Logo
│   └── functions/              # Cloudflare Pages Functions (API)
│       └── api/
│           ├── deploy.js       # POST /api/deploy
│           ├── teardown.js     # POST /api/teardown
│           ├── destroy.js      # POST /api/destroy
│           ├── status.js       # GET /api/status
│           └── health.js       # GET /api/health
├── README.md                   # This file
├── SECURITY.md                 # Security documentation
├── DEPLOYMENT.md               # Deployment guide
└── wrangler.toml               # Wrangler configuration
```

## 🔧 Setup

The control panel infrastructure is created by Terraform when you run `make up`. The actual Pages deployment happens automatically via the Makefile (if `CLOUDFLARE_API_TOKEN` is set) or via GitHub Actions.

### Required Secrets

Set these via **Cloudflare Dashboard** or **Wrangler CLI**:

#### Via Cloudflare Dashboard:
1. Go to **Cloudflare Dashboard** → **Pages** → **nexus-control**
2. **Settings** → **Environment Variables**
3. Add **Production** variables:
   - `GITHUB_OWNER` = `stefanko-ch` (auto-set by Terraform)
   - `GITHUB_REPO` = `Nexus-Stack` (auto-set by Terraform)
   - `GITHUB_TOKEN` = Your GitHub Personal Access Token (**Secret**)

#### Via Wrangler CLI:
```bash
cd control-panel/pages
npx wrangler pages secret put GITHUB_TOKEN --project-name=nexus-control
```

### GitHub Token Requirements

Create a Personal Access Token with:
- **Scope:** `repo` (full control of private repositories)
- **Or:** `public_repo` + `workflow` (for public repos)

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
| **Torn Down** | Infrastructure stopped, control panel + R2 active |
| **Destroyed** | Everything deleted (first deployment) |
| **Running** | Workflow in progress, please wait |

## 🧪 Local Development

Pages Functions can be tested locally with Wrangler:

```bash
cd control-panel/pages
npx wrangler pages dev .
```

Access at `http://localhost:8788`

## 🐛 Troubleshooting

### "Failed to trigger workflow"
- Check `GITHUB_TOKEN` is set correctly
- Verify token has `workflow` scope
- Check `GITHUB_OWNER` and `GITHUB_REPO` match your repository

### "Failed to fetch status"
- Same as above - token permissions issue

### Workflows not appearing
- Wait a few seconds for GitHub API propagation
- Check workflows exist in `.github/workflows/`

## 📝 Deployment Flow

```bash
# Initial setup
make init

# Deploy infrastructure (including control panel)
make up

# Set GitHub token secret
# → Via Cloudflare Dashboard (see above)
# → Or via Wrangler CLI

# Control panel is now live at https://control.YOUR_DOMAIN
```

## 🔄 Updates

When you update the control panel:

```bash
git add control-panel/
git commit -m "feat: Update control panel UI"
git push

# Cloudflare Pages auto-deploys on push
```

No manual deployment needed - Cloudflare Pages watches the `main` branch.

---

**Note:** The control panel **survives teardown** but is **destroyed** on `destroy-all`.
