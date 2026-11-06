---
title: "Hasura"
---

## Hasura

![Hasura](https://img.shields.io/badge/Hasura-1EB4D4?logo=hasura&logoColor=white)

**Instant GraphQL and REST API over PostgreSQL**

Hasura generates a GraphQL API from a PostgreSQL schema. Every table gets queries, mutations and realtime subscriptions, with relationships, filtering and pagination. Saved queries can also be served as REST endpoints, and row- and column-level permissions are declared per role.

| Setting | Value |
|---------|-------|
| Default Port | `8114` (bound to `127.0.0.1` on the host) |
| Console | `https://hasura.<domain>/console` |
| In-cluster API | `http://hasura:8080/v1/graphql` |
| Suggested Subdomain | `hasura` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Admin secret, generated per deployment (Infisical folder `hasura`) |
| Persistence | Dedicated PostgreSQL (`hasura-db`) in a Docker volume |
| Website | [hasura.io](https://hasura.io) |
| Source | [GitHub](https://github.com/hasura/graphql-engine) |

### Hasura next to PostgREST

[PostgREST](postgrest.md) maps tables to a REST API. Hasura is the GraphQL option, with subscriptions and a console for permissions and relationships.

### First steps

1. Open the console and enter the admin secret: Infisical, folder `hasura`, key `HASURA_ADMIN_SECRET`. The console keeps it in the browser.
2. Under **Data**, create a table in the `default` database. That database is `hasura-db`, Hasura's own PostgreSQL. A table created in the console is tracked, so it is in the API at once. A table created with any other SQL client is not: track it under **Data → default → public → Untracked tables** first.
3. Under **API**, query it right away:

```graphql
query {
  cities(order_by: { pop: desc }) {
    name
    pop
  }
}
```

From a notebook on `app-network`:

```python
import requests

r = requests.post(
    "http://hasura:8080/v1/graphql",
    json={"query": "{ cities { name pop } }"},
    headers={"x-hasura-admin-secret": "<HASURA_ADMIN_SECRET>"},
)
```

Other PostgreSQL databases, such as the shared `postgres` stack, can be added under **Data → Connect database**.

### Authentication

Every request needs the admin secret in `x-hasura-admin-secret`. Without it Hasura answers `access-denied`. The deploy refuses to start Hasura without one, because Hasura would otherwise serve its whole API, schema changes included, to anyone who reaches it. Telemetry is off.

### Persistence

Tables and Hasura's metadata live in `hasura-db`, a PostgreSQL 17 in the `hasura-db-data` volume.

- **`rebuild` (default): the data does not survive a teardown.** Hasura is not in the R2 backup list.
- **`snapshot`: the data survives**, because the whole disk is imaged.
