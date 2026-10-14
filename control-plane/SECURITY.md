# Security Considerations

## 🔒 Control Plane Security Architecture

### Token Protection

**GitHub Personal Access Token** is **never exposed** to the frontend:

```
┌─────────────────────────────────────────────────┐
│  Browser (Frontend)                             │
│  ✗ No access to GITHUB_TOKEN                    │
│  ✓ Only calls /api/* endpoints                  │
└─────────────────────────────────────────────────┘
                    ↓ HTTPS
┌─────────────────────────────────────────────────┐
│  Cloudflare Pages Functions (Server-side)       │
│  ✓ Has access to env.GITHUB_TOKEN               │
│  ✓ Validates requests                           │
│  ✓ Calls GitHub API with token                  │
└─────────────────────────────────────────────────┘
                    ↓ HTTPS + Bearer Token
┌─────────────────────────────────────────────────┐
│  GitHub Actions API                             │
│  ✓ Triggers workflows                           │
└─────────────────────────────────────────────────┘
```

### Access Control Layers

1. **Cloudflare Access** (Layer 1)
   - Email-based authentication (OTP)
   - The admin, the user addresses and the guest addresses can reach
     `control.domain.com`; Access does not distinguish between them
   - Session: 24 hours
   - Access covers `control.<domain>` and nothing else. Every other
     hostname the Pages project answers on — `<project>.pages.dev` and
     the per-deployment preview hostnames — is closed by the hostname
     check in Layer 2 instead. OpenTofu briefly managed an Access
     application for the production `pages.dev` hostname; it was removed
     because owning it means owning whatever policy an operator attached,
     and on the first real run that was a *reusable* account-level policy
     shared with other applications, which the plan would have renamed
     and rewritten. See the comment in `tofu/control-plane/main.tf`

2. **The Control Plane's own checks** (Layer 2)
   - `functions/_middleware.js` answers only on the Control Plane's own
     hostname and returns 404 on every other one — including the
     `pages.dev` production and preview hostnames. Not a redirect: a
     redirect would confirm which hostname is the real one
   - `functions/api/_utils/access-jwt.js` verifies the Access token:
     the RS256 signature against the team's JWKS, plus `iss`, `aud` and
     `exp`. The `Cf-Access-Authenticated-User-Email` header is not read
     anywhere — a header is something a caller can set
   - Every endpoint names a guard: `requireAdmin`, `requireOperator` or
     `requireViewer`. The two that intentionally need none — the health
     check and the version banner — are listed in
     `test/endpoint-guards.test.mjs`, which fails if a new one appears
   - A deployment that cannot verify tokens (no `ACCESS_AUD` or
     `ACCESS_TEAM_DOMAIN`) denies every request and names the missing
     value, rather than falling back to trusting the header

3. **Pages Functions** (Layer 3)
   - Server-side code execution
   - Environment variables isolated from frontend
   - No CORS issues (same origin)

4. **GitHub Token Scope** (Layer 4)
   - Token requires `workflow` permission only
   - Limited to triggering workflows
   - Does not grant repo write access

### Environment Variables

**Public** (set in Terraform):
- `GITHUB_OWNER` - Repository owner username
- `GITHUB_REPO` - Repository name

**Secret** (set manually):
- `GITHUB_TOKEN` - Personal Access Token with `workflow` scope

**Where to set secrets:**

```bash
# Option 1: Cloudflare Dashboard
# Pages → nexus-{domain}-control → Settings → Environment Variables
# Add as "Secret" (encrypted)

# Option 2: Wrangler CLI (replace {domain} with your domain, e.g., nexus-stefanko-ch-control)
npx wrangler pages secret put GITHUB_TOKEN --project-name=nexus-{domain}-control
```

### Token Requirements

**For Classic Personal Access Tokens:**

```
✓ workflow          - Trigger GitHub Actions workflows
✓ repo              - Full control of repositories (includes Secrets write access)
```

**For Fine-Grained Personal Access Tokens:**

Required permissions:
- **Repository access:** Select the specific repository (`Nexus-Stack`)
- **Repository permissions:**
  - `Actions: Write` - Trigger GitHub Actions workflows (Deploy/Teardown/Destroy)
  - `Secrets: Write` - Write repository secrets (for auto-saving R2 credentials)
  - `Contents: Read` - Read repository contents (required for branch access when triggering workflows)

**Not needed:**
- ✗ `write:packages`
- ✗ `delete_repo`
- ✗ `admin:org`
- ✗ `gist`
- ✗ `user`
- ✗ `Contents: Write` (read-only is sufficient)

**Important Notes:**
- Fine-Grained Tokens require explicit repository selection
- Make sure the token has access to the correct repository
- Token expiration must be set appropriately (or no expiration)
- Fine-Grained Tokens work the same way as Classic Tokens for API calls

### Attack Surface Analysis

| Attack Vector | Mitigation |
|---------------|------------|
| Token theft from frontend | ✅ Token never sent to browser |
| CSRF | ✅ `requireSameOrigin` on every state-changing endpoint, plus a verified Access session |
| A request on a hostname nobody protected | ✅ The middleware answers on one hostname and 404s the rest |
| A self-set `Cf-Access-*` identity header | ✅ The header is not read; the token's signature is verified |
| One Access identity acting as another | ✅ Per-endpoint guards compare the verified identity to `ADMIN_EMAIL` / `USER_EMAIL` |
| Token in git history | ✅ Token set via env vars, not committed |
| Man-in-the-middle | ✅ All traffic via HTTPS + Cloudflare proxy |
| Brute force | ✅ Cloudflare Access rate limiting |
| Unauthorized workflow trigger | ✅ Token requires authentication |

### Best Practices

1. **Token Rotation**
   - Rotate GitHub token every 90 days
   - Use token with minimal required scope
   - Delete old tokens immediately

2. **Access Control**
   - Keep `admin_email` list minimal
   - Use dedicated email for admin access
   - Review Cloudflare Access logs regularly

3. **Monitoring**
   - Monitor GitHub Actions usage
   - Check for unexpected workflow runs
   - Enable GitHub notifications for workflow triggers

4. **Separation of Concerns**
   - Control Plane uses dedicated token
   - Different from deployment secrets
   - No cross-contamination

### Incident Response

**If token is compromised:**

1. **Immediately revoke** the token at https://github.com/settings/tokens
2. Generate a new token with same scope
3. Update in Cloudflare Dashboard or via Wrangler
4. Review recent workflow runs for unauthorized activity
5. Check GitHub audit log

### Compliance

- ✅ Token stored encrypted in Cloudflare
- ✅ Access logs available via Cloudflare
- ✅ No PII stored (except admin email for auth)
- ✅ GDPR compliant (Cloudflare EU data centers available)

### Security Audit Checklist

- [ ] GitHub token has minimal scope (`workflow` only)
- [ ] Token set as **Secret** in Cloudflare (not plain env var)
- [ ] Cloudflare Access configured with correct admin email
- [ ] No hardcoded credentials in code
- [ ] HTTPS enforced (Cloudflare proxy)
- [ ] Session duration reasonable (24h)
- [ ] Token rotation schedule defined

---

**Questions or security concerns?**  
Open an issue at https://github.com/stefanko-ch/Nexus-Stack/issues
