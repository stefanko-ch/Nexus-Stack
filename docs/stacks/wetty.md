---
title: "Wetty"
---

## Wetty

![Wetty](https://img.shields.io/badge/Wetty-000000?logo=gnubash&logoColor=white)

**Web-based SSH terminal**

A terminal over HTTP/HTTPS that allows you to access your server via a web browser. Provides a full terminal experience without requiring SSH client software.

**Features:**
- **Browser-based SSH** - Access server terminal from any device with a web browser
- **No SSH client needed** - Useful for environments where SSH client installation is restricted
- **Full terminal experience** - Complete terminal functionality in your browser
- **Cloudflare Access protected** - Secure access via email OTP authentication
- **Public key authentication only** - No password authentication for enhanced security
- **Short session duration** - Cloudflare Access sessions expire after 1 hour for enhanced security
- **Optional** - enable it in the Control Plane like any other stack. It is not
  a core service; `services.yaml` carries no `core: true` for it. (This line
  used to claim the opposite.)

**Security Features:**
- ✅ **Public key authentication only** - `SSHAUTH=publickey` prevents password-based logins
- ✅ **Cloudflare Access** - Email OTP required before accessing Wetty interface
- ✅ **Short session duration** - Cloudflare Access sessions expire after 1 hour (enhanced security)
- ✅ **Rate limiting** - Cloudflare Access provides built-in rate limiting
- ✅ **HTTPS only** - All traffic encrypted via Cloudflare Tunnel
- ✅ **No direct SSH exposure** - SSH daemon only accessible via localhost

**Use cases:**
- Quick terminal access without setting up SSH clients
- Educational demos and teaching server management
- Access from devices where SSH client installation is restricted
- Fallback terminal access method via browser
- Emergency access when SSH client is unavailable

| Setting | Value |
|---------|-------|
| Default Port | `3002` |
| Suggested Subdomain | `wetty` |
| Public Access | **Never** (always protected) |
| Default Enabled | **No** (enable via Control Plane when needed) |
| Authentication | Public key only (no passwords) |
| Cloudflare Access Session | 1 hour (re-authentication required) |
| Website | [GitHub](https://github.com/butlerx/wetty) |
| Source | [GitHub](https://github.com/butlerx/wetty) |

> ✅ **Auto-configured:** Wetty connects to the server's SSH daemon using public key authentication only. Users must have their SSH public key configured on the server (same as regular SSH access).

> 🔒 **Security:** Wetty is configured with `SSHAUTH=publickey` to prevent password-based authentication. Only users with SSH keys configured on the server can access the terminal.

> 💡 **Usage:** Enable Wetty via the Control Plane when you need browser-based terminal access. It's disabled by default to reduce attack surface.
