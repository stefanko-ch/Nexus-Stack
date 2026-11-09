---
title: "Baserow"
---

## Baserow

![Baserow](https://img.shields.io/badge/Baserow-5190EF?logo=baserow&logoColor=white)

**No-code database**

Baserow gives a PostgreSQL database a spreadsheet interface. It has linked records, lookups, formulas, forms, and kanban, calendar and gallery views, and every table gets a REST API. It is an open-source alternative to Airtable, next to [NocoDB](nocodb.md).

| Setting | Value |
|---------|-------|
| URL | `https://baserow.<domain>` |
| Login | The stack user's email, admin of the instance |
| Credentials | Password generated per deployment (Infisical folder `baserow`) |
| Persistence | Docker volume `baserow-data` |
| Licence | MIT for the open-source edition; the image also contains premium and enterprise code under its own licence, inactive without a key |
| Website | [baserow.io](https://baserow.io) |

### First steps

1. Open `https://baserow.<domain>` and log in with `BASEROW_EMAIL` and `BASEROW_PASSWORD` from Infisical.
2. Create a workspace and a database, then a table. Columns can link to rows of another table, and lookups and formulas build on those links.
3. Under **Settings → Database tokens**, create a token for the REST API:

```python
import requests

token = "<database token>"
requests.get("https://baserow.<domain>/api/database/rows/table/<table id>/?user_field_names=true",
             headers={"Authorization": f"Token {token}"}).json()
```

From inside the server network the API is at `http://baserow/api/`. Baserow checks the `Host` header against its public URL, so a request there needs `Host: baserow.<domain>`.

### The admin account

**Baserow makes whoever signs up first the instance's admin.** So `baserow-init` claims that account on the first start, then switches new sign-ups off:

1. It creates the account with the stack user's email and the generated password, through the API.
2. It turns off the instance setting **Allow creating new accounts**.

On every later start it logs in and makes sure sign-ups are still off. If the stored password no longer matches Infisical, it fails with a message instead of leaving the setting unchecked. Further users are invited from **Admin → Users**.

Tested:
- the account was created on the first start and logged in as staff (admin);
- a second sign-up was refused with `ERROR_DISABLED_SIGNUP`;
- a wrong password was refused;
- the account and setting survived a recreate.

Between the container becoming healthy and `baserow-init` finishing there are a few seconds in which the sign-up page is still open. The site is behind Cloudflare Access during that time, so only someone who can pass Access could reach it.

### Resources

The all-in-one image runs Baserow's backend, the web frontend, Celery workers, PostgreSQL, Redis and Caddy in one container. With one web worker and one Celery worker it used about 1.25 GB. With the image's defaults (three web workers) it reached 1.8 GB, so the defaults are lowered. The container limit is 2.5 GB.

### Persistence

The database, uploads and the generated secret keys are in `baserow-data`.

- **`rebuild` (default): they do not survive a teardown.** Baserow is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
