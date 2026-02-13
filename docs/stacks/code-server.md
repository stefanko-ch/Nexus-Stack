## code-server

![code-server](https://img.shields.io/badge/code--server-007ACC?logo=visualstudiocode&logoColor=white)

**VS Code in the browser**

Run VS Code on a remote server and access it through the browser. Provides a consistent development environment accessible from any device. Features include:
- Full VS Code experience in the browser
- Extension marketplace support
- Integrated terminal
- Git integration
- Multi-language support

| Setting | Value |
|---------|-------|
| Default Port | `8100` |
| Suggested Subdomain | `code` |
| Public Access | No (development environment) |
| Website | [coder.com](https://coder.com) |
| Source | [GitHub](https://github.com/coder/code-server) |

### Usage

1. Enable the code-server service in the Control Plane
2. Access `https://code.YOUR_DOMAIN`
3. Authentication is handled by Cloudflare Access (no additional password)
4. Files are persisted in a Docker volume (`code-server-data`)
