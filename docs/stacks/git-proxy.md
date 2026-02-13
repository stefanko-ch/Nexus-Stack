## Git Proxy

![Git Proxy](https://img.shields.io/badge/Git_Proxy-009639?logo=nginx&logoColor=white)

**Public HTTPS Git access for external tools (Databricks, CI/CD)**

Nginx reverse proxy that forwards Git HTTPS requests to Gitea. Provides public Git clone/push/pull access for external tools without exposing the Gitea Web UI.

| Setting | Value |
|---------|-------|
| Default Port | `3201` (-> internal 80) |
| Suggested Subdomain | `git` |
| Public Access | Yes (no Cloudflare Access) |

### How It Works

```
External tools ──HTTPS──> git.<domain> (PUBLIC)
                               │ (Cloudflare Tunnel)
                         Nginx (:3201)
                               │ (proxy_pass)
                         Gitea (:3000) (PRIVATE)
```

- External tools (Databricks) use `https://git.<domain>/<user>/<repo>.git` with Gitea PAT
- Internal services (Jupyter, etc.) use `http://gitea:3000` directly via Docker network
- Gitea Web UI at `https://gitea.<domain>` remains private (Cloudflare Access OTP)

### Usage with Databricks

1. Create a Personal Access Token (PAT) in Gitea
2. In Databricks, add Git Credentials: select "GitHub" provider, use Gitea username + PAT
3. Clone repos via: `https://git.<domain>/<user>/<repo>.git`
