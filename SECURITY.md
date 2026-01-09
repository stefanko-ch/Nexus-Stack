# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Nexus-Stack, please report it responsibly.

### How to Report

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email: **sk@stefanko.ch**

Or use [GitHub's private vulnerability reporting](https://github.com/stefanko-ch/Nexus-Stack/security/advisories/new).

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution Target**: Within 30 days (depending on severity)

## Security Best Practices

When using Nexus-Stack:

1. **Never commit secrets** - Keep `config.tfvars` out of version control
2. **Use strong API tokens** - Rotate Hetzner and Cloudflare tokens periodically
3. **Limit Cloudflare token permissions** - Only grant required permissions
4. **Keep software updated** - The server has automatic security updates enabled
5. **Review Access policies** - Regularly audit who has access via Cloudflare Access

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| < 1.0   | :x:                |

## Security Features

Nexus-Stack is designed with security in mind:

- **Zero open ports** - All traffic routes through Cloudflare Tunnel
- **Cloudflare Access** - Email-based authentication by default
- **Automatic updates** - Ubuntu unattended-upgrades enabled
- **Fail2ban** - Intrusion prevention installed
- **No direct SSH** - SSH access only via Cloudflare Tunnel
