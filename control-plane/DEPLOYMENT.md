# Control Plane Deployment Checklist

> ⚠️ **Control Plane is deployed automatically via GitHub Actions workflows.**
> Manual deployment is for debugging only.

## Pre-Deployment

- [ ] Review code changes
- [ ] Security audit completed (see [SECURITY.md](SECURITY.md))
- [ ] All files in `control-plane/` directory

## GitHub Setup

- [ ] Create GitHub Personal Access Token
  - Go to https://github.com/settings/tokens
  - Click "Generate new token (classic)"
  - Select scope: `workflow`
  - Copy token (save securely, shown only once!)

## Infrastructure Variables

Ensure these are set in your `tofu/config.tfvars`:

```hcl
github_owner = "stefanko-ch"        # Your GitHub username
github_repo  = "Nexus-Stack"        # Repository name
```

## Deployment Steps

### 1. Deploy via GitHub Actions (Recommended)

```bash
# Run the initial setup workflow
gh workflow run initial-setup.yaml
```

This creates:
- ✅ Cloudflare Pages project (`nexus-{domain}-control`, e.g., `nexus-stefanko-ch-control`)
- ✅ DNS record (`control.domain.com`)
- ✅ Cloudflare Access protection
- ✅ D1 database with schema
- ✅ All environment variables configured automatically

### 2. Set GitHub Token Secret

**Option A: Via Cloudflare Dashboard**

1. Go to **Cloudflare Dashboard**
2. Navigate to **Pages** → **nexus-{domain}-control**
3. Click **Settings** → **Environment Variables**
4. Click **Add variables**
5. Production tab:
   - Variable name: `GITHUB_TOKEN`
   - Value: `ghp_xxxxxxxxxxxxx` (paste your token)
   - ⚠️ Select **"Encrypt"** checkbox
6. Click **Save**

**Option B: Via Wrangler CLI**

```bash
cd control-plane/pages
# Replace {domain} with your domain (e.g., nexus-stefanko-ch-control)
npx wrangler pages secret put GITHUB_TOKEN --project-name=nexus-{domain}-control
# Paste token when prompted
```

### 3. Deploy Pages Project

**Automatic deployment:**

The control plane is automatically deployed:
- Via GitHub Actions workflow (`setup-control-plane.yaml`)
- Via GitHub Actions workflow (when triggered from control plane)

**Manual deployment (if needed):**

```bash
cd control-plane/pages
# Replace {domain} with your domain (e.g., nexus-stefanko-ch-control)
npx wrangler pages deploy . --project-name=nexus-{domain}-control
```

### 4. Verify Deployment

1. Visit `https://control.YOUR_DOMAIN`
2. Authenticate with Cloudflare Access (email OTP)
3. Should see Control Plane UI
4. Check status indicator (might show "unknown" initially)

### 5. Test Workflow Triggers

⚠️ **Test in this order to avoid destroying infrastructure:**

1. Click **"Deploy"** button
   - Should trigger `setup-control-plane.yaml` workflow
   - Check GitHub Actions tab for running workflow
   - Status should update to "Running"

2. After deployment completes:
   - Status should show "Deployed"
   - Workflow history shows successful run

3. Test **"Teardown"** (optional):
   - Only if you want to test teardown
   - Requires confirmation modal
   - Destroys Hetzner infrastructure (keeps control plane)

⚠️ **Do NOT test "Destroy"** unless you want to delete everything!

## Post-Deployment

- [ ] Control Plane accessible at `https://control.domain.com`
- [ ] Cloudflare Access authentication works
- [ ] Status API returns workflow data
- [ ] Deploy button triggers workflow successfully
- [ ] Workflow history displays correctly

## Troubleshooting

### "Failed to trigger workflow"

**Possible causes:**
1. GitHub token not set or expired
2. Token missing `workflow` scope
3. Wrong `GITHUB_OWNER` or `GITHUB_REPO`

**Solution:**
```bash
# Check env vars in Cloudflare Dashboard
Pages → nexus-{domain}-control → Settings → Environment Variables

# Verify token scope at:
https://github.com/settings/tokens
```

### "Failed to fetch status"

Same as above - token issue.

### Cloudflare Access loop

**Cause:** Wrong admin email or Access policy misconfigured

**Solution:**
```bash
# Check Terraform output
cd tofu
tofu output

# Verify admin_email matches Access policy
```

### Control Plane shows 404

**Cause:** Pages project not deployed

**Solution:**
```bash
cd control-plane/pages
# Replace {domain} with your domain (e.g., nexus-stefanko-ch-control)
npx wrangler pages deploy . --project-name=nexus-{domain}-control
```

## Maintenance

### Token Rotation (every 90 days)

1. Generate new token at https://github.com/settings/tokens
2. Update in Cloudflare Dashboard (Pages → Settings → Env Vars)
3. Delete old token from GitHub
4. Test workflow trigger

### Update Control Plane Code

Control Plane is automatically updated when you push to the main branch.
GitHub Actions will redeploy the Control Plane.

Or trigger manually:
```bash
gh workflow run setup-control-plane.yaml
```

## Rollback

If something goes wrong:

```bash
# Via Cloudflare Dashboard
# Pages → nexus-{domain}-control → Deployments → Previous deployment → Rollback
```

---

✅ **Deployment complete!** Visit `https://control.YOUR_DOMAIN`
