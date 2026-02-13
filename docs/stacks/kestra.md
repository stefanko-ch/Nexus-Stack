## Kestra

![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)

**Modern workflow orchestration for data pipelines & automation**

A powerful, event-driven workflow orchestration platform for building data pipelines, ETL processes, and infrastructure automation:
- Declarative YAML workflows
- Event-driven triggers (cron, webhooks, file, message queues)
- 400+ plugins (AWS, GCP, Azure, databases, APIs)
- Real-time execution monitoring
- Built-in code editor with live preview
- Docker-in-Docker task execution

| Setting | Value |
|---------|-------|
| Default Port | `8085` (→ internal 8080) |
| Suggested Subdomain | `kestra` |
| Public Access | **Never** (always protected) |
| Website | [kestra.io](https://kestra.io) |
| Source | [GitHub](https://github.com/kestra-io/kestra) |

> ✅ **Auto-configured:** Admin account (Basic Auth) is automatically configured during deployment. Credentials are available in Infisical.

### Architecture

The stack includes:
- **Kestra** - Main workflow engine with web UI
- **PostgreSQL** - Database for workflow state and metadata

> ℹ️ **Note:** Admin credentials are auto-generated. Credentials are available in Infisical.
