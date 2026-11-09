---
title: "Grist"
---

## Grist

![Grist](https://img.shields.io/badge/Grist-16B378?logoColor=white)

**Spreadsheet with a database underneath**

Grist is a spreadsheet whose tables have typed columns, references between tables and formulas written in Python. Each document is a SQLite file with its own REST API, and cards, charts and forms are built on the same tables. It sits between a spreadsheet and a database.

| Setting | Value |
|---------|-------|
| URL | `https://grist.<domain>` |
| Login | Your Cloudflare Access login — no separate Grist password |
| Admin | The stack user's email |
| Persistence | Docker volume `grist-data` |
| Image | `gristlabs/grist-oss`, the build with only the open-source code |
| Licence | Apache-2.0 |
| Website | [getgrist.com](https://www.getgrist.com) |

### First steps

1. Open `https://grist.<domain>`. You are already logged in: Grist uses the email you logged in to Cloudflare Access with.
2. Create a document, add a table, and give a column a formula such as `$Pages * 2`. Formulas are Python, so `$Title.upper()` or a multi-line function body work too.
3. For the API, create a key under your profile (**Profile Settings → API**):

```python
import requests

key = "<API key>"
requests.get("https://grist.<domain>/api/docs/<doc id>/tables/Books/records",
             headers={"Authorization": f"Bearer {key}"}).json()
```

### Login through Cloudflare Access

Grist has no password login of its own. Its options are an external identity provider or an email passed in a header by a proxy in front of it. Cloudflare Access is that proxy here:

- It puts the logged-in email in `Cf-Access-Authenticated-User-Email`, and Grist trusts that header (`GRIST_FORWARD_AUTH_HEADER`).
- Grist checks the header on every request (`GRIST_IGNORE_SESSION`).
- It forces login (`GRIST_FORCE_LOGIN`).
- **Log out** goes to Access's logout page.
- The stack user's email is Grist's install admin.

Tested by sending the header directly to the container:
- without the header, the site redirects to the login and the API sees no organisations;
- with the stack user's email, the account is the install admin;
- a document created that way was refused to a request without the header and to another email (`No view access`);
- data was kept across a restart.

The header is set by Cloudflare, so a browser cannot forge it through the tunnel. **A container on `app-network` that calls `http://grist:8484` directly can.** Treat Grist like the stacks without their own login: it relies on Access, and on nothing untrusted running on the server network.

### Formula sandbox

Formulas run in [gVisor](https://gvisor.dev), not in the server process (`GRIST_SANDBOX_FLAVOR=gvisor`). Without that setting the image runs them unsandboxed, with the server's own rights. gVisor worked in the unprivileged container in local tests (Docker Desktop, arm64). **It has not been tried on the server's kernel yet.** If it fails there, formulas stop calculating and the container log says why.

### Settings

- **Telemetry** (`GRIST_TELEMETRY_LEVEL`) is off.
- **The automatic version check** is off.
- **The anonymous playground** is off.
- **The first-run boot page and setup wizard** are skipped (`GRIST_IN_SERVICE`). They exist to choose an authentication method, which is set here.

### Resources

It used about 370 MB with the sandbox running. The container limit is 1 GB.

### Persistence

The home database and one SQLite file per document are in `grist-data`.

- **`rebuild` (default): they do not survive a teardown.** Grist is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.

A document can also be downloaded as a `.grist` file (it is SQLite) or as Excel or CSV.
