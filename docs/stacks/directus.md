---
title: "Directus"
---

## Directus

![Directus](https://img.shields.io/badge/Directus-6644FF?logo=directus&logoColor=white)

**REST and GraphQL APIs plus an admin app on a SQL database**

Directus serves every table of a SQL database as a REST and GraphQL API. Its admin app is for browsing and editing the data. It adds roles and permissions down to single fields, flows (event-driven automations) and dashboards. Here it manages its own PostgreSQL.

| Setting | Value |
|---------|-------|
| URL | `https://directus.<domain>` |
| Login | The stack user's email, administrator |
| Credentials | Password generated per deployment (Infisical folder `directus`) |
| Persistence | Docker volumes `directus-db-data`, `directus-uploads`, `directus-extensions` |
| Licence | Monospace Sustainable Core License (MSCL) — not an OSI licence; see below |
| Website | [directus.io](https://directus.io) |

### First steps

1. Open `https://directus.<domain>` and log in with `DIRECTUS_EMAIL` and `DIRECTUS_PASSWORD` from Infisical.
2. Under **Settings → Data Model**, create a collection (a table) with fields.
3. Add items in the content module. They are now in the API:

```python
import requests

base = "https://directus.<domain>"
token = requests.post(f"{base}/auth/login",
                      json={"email": "<DIRECTUS_EMAIL>", "password": "<DIRECTUS_PASSWORD>"}).json()["data"]["access_token"]
h = {"Authorization": f"Bearer {token}"}
requests.get(f"{base}/items/books", headers=h).json()
requests.post(f"{base}/graphql", headers=h, json={"query": "{ books { title } }"}).json()
```

For scripts, a static token set on a user (**User Directory → user → Token**) avoids the login call. Inside the server network the API is at `http://directus:8055`.

Tested:
- login, a collection created, an item written, then read through REST and GraphQL;
- anonymous reads refused;
- a wrong password refused (`INVALID_CREDENTIALS`);
- public registration refused;
- a second setup refused (`403`);
- data kept across a restart.

### The admin account

Directus creates its first admin at bootstrap, from `ADMIN_EMAIL` and `ADMIN_PASSWORD`. **If that fails, it starts anyway, healthy, with its setup page open, and whoever opens it first becomes admin.** It fails, for example, when Directus rejects the address as invalid.

`directus-init` closes that gap. After every start it checks that the admin logs in:

- **If no admin exists,** it claims the setup itself with the same values.
- **If the setup is refused too,** it fails with Directus's reason in its log, so the deploy shows the problem.

All three paths were tested: a normal start, a missing admin claimed by the init, and an address Directus refuses.

### Licence and telemetry

Directus is under the [Monospace Sustainable Core License](https://github.com/directus/directus/blob/main/license):
- it permits internal use, education and non-commercial use;
- it forbids a "competing use" such as reselling Directus as a service;
- each release converts to GPL-3.0 four years after its date.

The free core tier **sends anonymous telemetry, including the public URL, and the `TELEMETRY` setting is ignored on that tier** (per Directus's licensing docs). The one-time project owner registration is switched off.

### Persistence

The database is in `directus-db-data`, uploaded files in `directus-uploads`.

- **`rebuild` (default): they do not survive a teardown.** Directus is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
