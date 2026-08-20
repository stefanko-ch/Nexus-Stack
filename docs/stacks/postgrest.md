![PostgREST](https://img.shields.io/badge/PostgREST-2C3E50?logo=postgresql&logoColor=white)

# PostgREST — Auto-generated REST API for any Postgres schema

> ⚠️ **Security default — read before enabling.** The shipped configuration sets `PGRST_DB_ANON_ROLE=nexus-postgres`, the shared-Postgres **superuser**. Anyone reaching the API (gated by Cloudflare Access at the edge, but still authenticated *team members*) inherits full DB privileges — including DROP, DELETE-without-WHERE, and access to every table in every schema. This is acceptable for a single-operator lab/education setup. For multi-user or classroom deployments, **tighten this before enabling**: create a dedicated `web_anon` role with `SELECT`-only grants on the tables you want public (see the "Production hardening" section below).

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

The compose env (`PGRST_DB_URI`, `PGRST_DB_SCHEMAS`, `PGRST_DB_ANON_ROLE`, `PGRST_JWT_SECRET`) is populated by [`service_env._render_postgrest`](https://github.com/stefanko-ch/Nexus-Stack/blob/main/src/nexus_deploy/service_env.py) from the Tofu-generated `random_password.postgrest_jwt_secret` and the shared-Postgres password — both pushed to Infisical (`/postgrest/POSTGREST_JWT_SECRET` and the shared `POSTGRES_PASSWORD`).

```text
HTTPS client  →  Cloudflare Access  →  Cloudflare Tunnel  →  postgrest:3000  →  postgres:5432
                  (email OTP)                                    (Go binary)        (shared)
```

## Try it out (Marimo notebook)

A seeded Marimo notebook walks through the full PostgREST API surface — list / filter / order / paginate, POST / PATCH / DELETE, and fetching the OpenAPI spec — using only stdlib (`urllib.request` + `json`, no extra `pip install`). If both **Marimo** and **PostgREST** are enabled and **Gitea** is enabled (so the workspace-repo seed lands), open `https://marimo.<domain>` and look for `nexus_seeds/marimo/Getting_Started_PostgREST.py`.

The notebook hits PostgREST at the internal `http://postgrest:3000` — bypassing Cloudflare Access since both containers share `app-network`. Source: [`examples/workspace-seeds/marimo/Getting_Started_PostgREST.py`](https://github.com/stefanko-ch/Nexus-Stack/blob/main/examples/workspace-seeds/marimo/Getting_Started_PostgREST.py).

## Typical workflow

1. **Create your schema** in the shared `postgres` stack — via [CloudBeaver](./cloudbeaver.md), [pgAdmin](./pgadmin.md), [Adminer](./adminer.md), or `psql`. Use the `public` schema (default) or add a custom schema and update `PGRST_DB_SCHEMAS`.

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

## Production hardening — replace the superuser anon role

For multi-user or classroom deployments, the most important hardening is **swapping the anon role away from the shared-Postgres superuser** so anonymous traffic isn't all-privileged. One-time SQL setup in the shared `postgres` stack (run via CloudBeaver / psql):

```sql
-- Dedicated role for anonymous PostgREST traffic. NOLOGIN — only
-- reachable via PostgREST's role-switch, never via direct connection.
CREATE ROLE web_anon NOLOGIN;

-- Allow it to access the public schema, but only the tables/columns
-- you grant explicitly.
GRANT USAGE ON SCHEMA public TO web_anon;

-- Per-table grants (repeat for each table you want public). Start
-- with SELECT-only; widen to INSERT/UPDATE/DELETE only where intended.
GRANT SELECT ON public.your_table TO web_anon;
```

Then in the Control Plane env-edit flow (or by editing `stacks/postgrest/.env` directly on the server and `docker compose up -d --force-recreate postgrest`):

```bash
PGRST_DB_ANON_ROLE=web_anon
```

After the change, `curl https://postgrest.<domain>/your_table` still works (read-only), but `DELETE`, `INSERT`, and access to non-granted tables now return `401`. For non-anonymous higher-privileged operations, clients send a JWT with a different `role` claim.

## Caveats

- **Schema cache.** New tables / columns require a SIGUSR1 reload or container restart. PostgREST does not poll the schema.

- **PostgREST inherits Postgres' RBAC fully** — a misconfigured GRANT means an anonymous DELETE works. After tightening to `web_anon`, always verify with `\dp public.your_table` in psql before trusting the grant.

## Documentation

- [PostgREST Tutorials](https://postgrest.org/en/stable/tutorials/) — step-by-step from zero to JWT-authenticated API
- [API Reference](https://postgrest.org/en/stable/references/api.html) — filtering, embedding, RPC syntax
