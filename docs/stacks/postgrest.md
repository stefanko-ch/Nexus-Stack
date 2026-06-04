![PostgREST](https://img.shields.io/badge/PostgREST-2C3E50?logo=postgresql&logoColor=white)

# PostgREST — Auto-generated REST API for any Postgres schema

PostgREST turns any Postgres database into a fully-featured REST API by introspecting its schema. Tables, views, and stored functions become endpoints with built-in filtering, ordering, pagination, embedded resources, and content negotiation (JSON, CSV). Zero schema definitions on the PostgREST side — the API surface **is** the database surface.

The auto-generated OpenAPI spec at the root (`/`) makes it trivial to explore in any Swagger-style UI; paste the URL into Hoppscotch for an interactive playground.

| Setting | Value |
|---------|-------|
| Image | `postgrest/postgrest:v14.12` |
| Port | `3009` (host) → `3000` (container) |
| Suggested Subdomain | `postgrest` → `https://postgrest.YOUR_DOMAIN` |
| Public Access | No — behind Cloudflare Access (email OTP) |
| Backing Database | The shared `postgres` stack on `app-network` |
| Connection Role | `nexus-postgres` (the shared-Postgres superuser) |
| Default Schema | `public` |
| Website | [postgrest.org](https://postgrest.org) |
| Source | [GitHub](https://github.com/PostgREST/postgrest) |

## How it works

The compose env (`PGRST_DB_URI`, `PGRST_DB_SCHEMAS`, `PGRST_DB_ANON_ROLE`, `PGRST_JWT_SECRET`) is populated by [`service_env._render_postgrest`](../../src/nexus_deploy/service_env.py) from the Tofu-generated `random_password.postgrest_jwt_secret` and the shared-Postgres password — both pushed to Infisical (`/postgrest/POSTGREST_JWT_SECRET` and the shared `POSTGRES_PASSWORD`).

```
HTTPS client  →  Cloudflare Access  →  Cloudflare Tunnel  →  postgrest:3000  →  postgres:5432
                  (email OTP)                                    (Go binary)        (shared)
```

## Typical workflow

1. **Create your schema** in the shared `postgres` stack — via [CloudBeaver](https://nexus-stack.ch/docs/stacks/cloudbeaver), [pgAdmin](https://nexus-stack.ch/docs/stacks/pgadmin), [Adminer](https://nexus-stack.ch/docs/stacks/adminer), or `psql`. Use the `public` schema (default) or add a custom schema and update `PGRST_DB_SCHEMAS`.

2. **Reload PostgREST's schema cache.** PostgREST caches the introspected schema at startup; new tables won't appear until you signal a reload. From inside the container:

   ```bash
   docker exec postgrest kill -SIGUSR1 1
   ```

   …or restart the container via Portainer. (A `LISTEN`-based hot reload is configurable upstream but kept off here for simplicity.)

3. **Hit the API.** Every table in the configured schema is now an endpoint:

   ```bash
   # List rows
   curl https://postgrest.YOUR_DOMAIN/my_table

   # Filter + order + paginate
   curl 'https://postgrest.YOUR_DOMAIN/my_table?col=eq.foo&order=created_at.desc&limit=10'

   # Insert a row
   curl -X POST https://postgrest.YOUR_DOMAIN/my_table \
     -H 'Content-Type: application/json' \
     -d '{"col":"bar"}'

   # Get the OpenAPI spec
   curl https://postgrest.YOUR_DOMAIN/
   ```

4. **Auth (JWT).** For non-anonymous requests, mint a short-lived HS256 token signed with `POSTGREST_JWT_SECRET` (found in Infisical at `/postgrest/POSTGREST_JWT_SECRET`). The token's `role` claim names the Postgres role PostgREST switches to for that request:

   ```bash
   # Example token (mint with any HS256 library, e.g. jwt.io or python-jose)
   curl https://postgrest.YOUR_DOMAIN/restricted_table \
     -H "Authorization: Bearer ${JWT}"
   ```

## Caveats

- **Anon role is the superuser.** The default `PGRST_DB_ANON_ROLE=nexus-postgres` means anonymous requests have the same DB privileges as the connection user — fine for the lab/education setup, **not** production-grade. Tighten by creating a dedicated `web_anon` role with `SELECT`-only grants on the tables you want public, and updating the env var.

- **Schema cache.** New tables / columns require a SIGUSR1 reload or container restart. PostgREST does not poll the schema.

- **No write-row-by-row safety.** PostgREST inherits Postgres' RBAC fully — a misconfigured GRANT means an anonymous DELETE works. Always test grants against `nexus-postgres` privileges before trusting them.

## Documentation

- [PostgREST Tutorials](https://postgrest.org/en/stable/tutorials/) — step-by-step from zero to JWT-authenticated API
- [API Reference](https://postgrest.org/en/stable/references/api.html) — filtering, embedding, RPC syntax
