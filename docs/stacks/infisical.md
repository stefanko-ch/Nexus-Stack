---
title: "Infisical"
---

## Infisical

![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)

**Open-source secret management platform**

A modern, developer-friendly alternative to HashiCorp Vault:
- Beautiful, intuitive UI
- No unsealing required (unlike Vault)
- Environment variables sync to your apps
- Team collaboration with RBAC
- Audit logs for compliance
- Native integrations (Kubernetes, Docker, CI/CD)

| Setting | Value |
|---------|-------|
| Default Port | `8070` |
| Suggested Subdomain | `infisical` |
| Public Access | **Never** (always protected) |
| Website | [infisical.com](https://infisical.com) |
| Source | [GitHub](https://github.com/Infisical/infisical) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. A "Nexus Stack" project is created with all generated passwords pre-loaded. Credentials are available in Infisical.

> ℹ️ **Note:** Secrets are auto-generated on first deployment (encryption key, auth secret). These are stored in `stacks/infisical/.env`.

### The bundled PostgreSQL

Infisical brings its own database, `infisical-db`, on `postgres:18-alpine`.
It is not the shared `postgres` stack — that one is optional and off by
default, while Infisical is a core service that has to come up on every
spin-up.

Note the mount: **`/var/lib/postgresql`, not `/var/lib/postgresql/data`**.
From 18 the image stores the cluster in a major-versioned subdirectory
(`/var/lib/postgresql/18/docker`), so the mount goes one level up. With the
pre-18 path the container exits 1 on start rather than writing somewhere
unexpected — the failure is loud, but total. The four other stacks on 18
mount the same way.

**Why 18.** Infisical's own requirements page says it has "extensively
tested" PostgreSQL 16 and recommends "versions 14 and up", and says nothing
about anything newer — so this was checked directly instead. Running
`infisical/infisical:v0.155.5` against 16, 17 and 18 produces the same 713
migrated tables and a `200` from `/api/status` on all three; the only log
error is an unrelated SMTP connection refusal. 18 is therefore not a
gamble, it is where the rest of this project's databases already are, and
it is supported until **2030-11-14**. The 14 it replaces reaches end of
life on **2026-11-12**.

### Changing the major version

What it costs depends on which lifecycle the stack runs — see
[snapshot-lifecycle.md](../admin-guides/snapshot-lifecycle.md).

**Rebuild lifecycle: nothing to do.** The teardown destroys the server and
the `infisical-db-data` volume with it. Postgres initialises an empty
cluster, Infisical runs its own migrations against it, and the spin-up
recreates the admin account and pushes every managed secret back. That is
the normal state of affairs for this stack, not a special case for a
version bump.

**Snapshot lifecycle: the data directory comes back.** It holds a cluster
written by the old major, and PostgreSQL refuses to start against it. The
`pg-preflight` phase stops the deploy before that happens and names both
versions:

```text
❌ PostgreSQL data directory was written by a different major version.

     infisical/infisical-db: data is PostgreSQL 14, image is 18  (volume infisical_infisical-db-data)
```

At that point `infisical-db` is **not running** — the preflight stopped the
deploy before compose-up — so `docker exec infisical-db pg_dump` has nothing
to attach to. Start a temporary PostgreSQL 14 against the volume instead. It
mounts at the *old* path, because that is the layout the volume still has:

```bash
ssh nexus "docker run --rm -u postgres \
  -v infisical_infisical-db-data:/var/lib/postgresql/data \
  --entrypoint sh postgres:14-alpine -c \
  'pg_ctl -D /var/lib/postgresql/data -o \"-c listen_addresses=\" -w start >/dev/null \
   && pg_dump -U nexus-infisical -Fc infisical'" > infisical-pg14.dump
```

`listen_addresses=` keeps the temporary server on its socket only, so nothing
can reach it while it runs. Check the result before continuing — the file
starts with `PGDMP`:

```bash
head -c 5 infisical-pg14.dump   # PGDMP
```

Then discard the volume and deploy again:

```bash
ssh nexus "cd /opt/docker-server/stacks/infisical && docker compose down"
ssh nexus "docker volume rm infisical_infisical-db-data"
```

Everything Nexus-Stack manages returns on the next spin-up — the admin
account and all generated service credentials are re-pushed. What does
**not** return is anything you added by hand in the Infisical UI: your own
secrets, extra projects and users, and the audit log.

If the stack holds any of that, restore it once Infisical has started and
created its schema, so the restore lands on a database that exists:

```bash
ssh nexus "docker exec -i infisical-db pg_restore -U nexus-infisical \
  -d infisical --clean --if-exists" < infisical-pg14.dump
ssh nexus "cd /opt/docker-server/stacks/infisical && docker compose restart infisical"
```

The `14 -> 18` round trip works — `pg_dump -Fc` is version-independent by
design and `pg_restore` reads the older format. Restore into a **new**
cluster, never over one Infisical has since written to.
