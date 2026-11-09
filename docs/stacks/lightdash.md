---
title: "Lightdash"
---

## Lightdash

![Lightdash](https://img.shields.io/badge/Lightdash-7262FF?logoColor=white)

**BI on top of dbt models**

Lightdash reads a dbt project and turns its models into explores. Dimensions and metrics are defined once in the dbt YAML, and charts and dashboards are built on them, so a dashboard shows the numbers the models define.

| Setting | Value |
|---------|-------|
| Default Port | `8117` (bound to `127.0.0.1` on the host; container port `8080`) |
| Suggested Subdomain | `lightdash` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Admin with the stack user's email, password generated per deployment (Infisical folder `lightdash`) |
| Persistence | Dedicated PostgreSQL (`lightdash-db`) and SeaweedFS as S3 (`lightdash-s3`) in Docker volumes |
| Website | [lightdash.com](https://www.lightdash.com) |
| Source | [GitHub](https://github.com/lightdash/lightdash) |

### Lightdash next to Metabase and Superset

[Metabase](metabase.md) and [Superset](superset.md) define metrics in the BI tool. Lightdash keeps them in the dbt project, in Git, next to the models that produce the data.

### Authentication

The first account registered becomes the admin of the one organization. After that, Lightdash lets in only invited users; a self-registration is refused. So that the first account is never a stranger, `lightdash-init` registers it on the first start: the stack user's email (`LIGHTDASH_EMAIL`) and a generated password (`LIGHTDASH_PASSWORD`), both in the Infisical folder `lightdash`. Invite further users from the organization settings.

On the start that registers the admin, `lightdash-init` checks that the generated account logs in with the admin role, and fails if it does not; reset `lightdash-db` to reclaim the admin then. On later starts it only logs in to confirm. If that login fails because the admin changed the password in Lightdash, it logs a warning and changes nothing; `LIGHTDASH_PASSWORD` in Infisical is then no longer the current password.

### First steps

1. Log in with the credentials from Infisical.
2. Create a project: pick the warehouse, for example the shared `postgres` stack (`postgres:5432`), and connect the dbt project. Whether Lightdash can pull a project straight from Forgejo has not been tested here. The route that needs no Git provider is the Lightdash CLI (`npm install -g @lightdash/cli`), run where the dbt project lives, for example in [code-server](code-server.md): `lightdash login http://lightdash:8080`, then `lightdash deploy --create`. Use the in-cluster address there: the public URL is behind Cloudflare Access, which a CLI cannot pass. This path has not been tested here either.
3. Tables from the dbt models appear as explores. Metrics are declared in the model YAML; the [Lightdash docs](https://docs.lightdash.com) describe the syntax for each dbt version.

### Not included

No headless browser runs with this stack, so scheduled deliveries and Slack unfurls that render chart images do not work. Telemetry and the update check are switched off.

### Persistence

The organization, users, projects and charts are in `lightdash-db`, and exports in `lightdash-s3`.

- **`rebuild` (default): the data does not survive a teardown.** Lightdash is not in the R2 backup list. Keep the dbt project in Git; charts and dashboards would have to be rebuilt.
- **`snapshot`: the data survives**, because the whole disk is imaged.

### Architecture

The image is published for `linux/amd64` only. The default servers are x86 (`cx43`), so it runs natively.
