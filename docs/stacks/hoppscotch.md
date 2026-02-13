## Hoppscotch

![Hoppscotch](https://img.shields.io/badge/Hoppscotch-201718?logo=hoppscotch&logoColor=white)

**Open-source API testing platform (Postman alternative)**

Hoppscotch is a lightweight, open-source API development ecosystem that offers a fast and beautiful interface for testing APIs. Features include:
- REST, GraphQL, WebSocket, and SSE support
- Team collaboration with shared workspaces
- Collections and environments management
- Pre-request and post-request scripts
- Authentication helpers (OAuth, Basic, Bearer, API Key)
- Request history and favorites
- Import/export with Postman, OpenAPI, and HAR formats

| Setting | Value |
|---------|-------|
| Default Port | `3003` |
| Suggested Subdomain | `hoppscotch` |
| Admin Path | `/admin` |
| Public Access | No (API testing tool) |
| Website | [hoppscotch.io](https://hoppscotch.io) |
| Source | [GitHub](https://github.com/hoppscotch/hoppscotch) |

### Architecture

The stack includes:
- **Hoppscotch AIO** - All-in-one container with frontend, backend, and admin
- **PostgreSQL** - Database for users, teams, and collections

### Authentication

Hoppscotch uses email magic links for authentication by default. No OAuth configuration is required.

> ℹ️ **Note:** This stack uses the official AIO (All-In-One) container which includes the main app, admin dashboard, and API backend in a single container.
