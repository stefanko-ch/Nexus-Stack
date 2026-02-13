## Woodpecker CI

![Woodpecker CI](https://img.shields.io/badge/Woodpecker_CI-4CAF50?logo=woodpeckerci&logoColor=white)

**Lightweight Docker-native CI/CD engine with pipeline-as-code**

Woodpecker CI is a simple, container-native continuous integration engine forked from Drone CI. Pipelines are defined in `.woodpecker.yml` files in your Git repositories and executed inside Docker containers.

**Features:**
- **Pipeline-as-code** - Define CI/CD pipelines in `.woodpecker.yml` files alongside your code
- **Docker-native** - Each pipeline step runs in its own container
- **Multi-forge support** - Integrates with GitHub, Gitea, GitLab, Bitbucket, and Forgejo
- **Lightweight** - Minimal resource usage compared to Jenkins or GitLab CI
- **Matrix builds** - Run pipeline variants across multiple configurations
- **Secrets management** - Built-in secret storage for pipeline credentials

| Setting | Value |
|---------|-------|
| Default Port | `8084` |
| Suggested Subdomain | `woodpecker` |
| Public Access | No (Cloudflare Access protected) |
| Default Enabled | No |
| Website | [woodpecker-ci.org](https://woodpecker-ci.org) |
| Source | [GitHub](https://github.com/woodpecker-ci/woodpecker) |

**Architecture (2 containers):**

| Container | Image | Purpose |
|-----------|-------|---------|
| `woodpecker-server` | `woodpeckerci/woodpecker-server:v3.13.0` | Web UI, API, and pipeline coordination |
| `woodpecker-agent` | `woodpeckerci/woodpecker-agent:v3.13.0` | Pipeline executor (runs Docker containers) |

**Authentication (auto-configured via Gitea):**
Woodpecker uses OAuth from Gitea for authentication. There is no built-in user/password system. The deploy script automatically creates a Gitea OAuth application and configures Woodpecker with the credentials. Log in via your Gitea account.

> **Dependency:** Woodpecker requires Gitea. If Woodpecker is enabled without Gitea, Gitea is auto-enabled during deployment.

**Data persistence:**
Woodpecker uses SQLite by default. The database is stored in the `woodpecker-server-data` Docker volume on the Hetzner persistent volume, ensuring data survives teardown and spin-up.
