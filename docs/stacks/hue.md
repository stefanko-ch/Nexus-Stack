---
title: "Hue"
---

## Hue

![Hue](https://img.shields.io/badge/Hue-4A90E2?logo=apachehadoop&logoColor=white)

**The SQL workbench, pointed at the engines you already run**

Schema tree, an editor with autocomplete, saved queries, charts over results — for PostgreSQL, Trino and ClickHouse.

| Setting | Value |
|---------|-------|
| Host Port | `8111` (container `8888`; 8888 belongs to jupyter here) |
| Suggested Subdomain | `hue` |
| Public Access | No (Cloudflare Access, **and** Hue's own login) |
| Website | [gethue.com](https://gethue.com) |
| Image | `gethue/hue:20260611-140101` — amd64 only |
| Credentials | `nexus-hue-admin` / Infisical `/hue/HUE_PASSWORD` |

### Three things this stack fixes about the image

**1. It ships a published Django secret key.** `/usr/share/hue/desktop/conf/z-hue-overrides.ini` contains the literal string `kasdlfjknasdfl3hbaksk3bwkasdfkasdfba23asdf`, readable by anyone who pulls the image. Django signs session cookies with it, so leaving it in place means a forgeable session. The entrypoint replaces the file with one carrying a generated 50-character key, and `_render_hue` refuses to render an empty one.

**2. It terminates its own supervisor at startup.** Without an init process the container exits 143 within seconds:

```
gunicorn_cleanup_utils WARNING  Found orphaned process: PID 33,
  CMD: .../python3.11 ./build/env/bin/supervisor
Terminated
```

Measured on three tags — `20260529-140101`, `20260611-140101` and `latest` — and on the **stock** image with no configuration of ours, so it is not caused by anything here. The cause is exact, from `gunicorn_cleanup_utils.cleanup_orphaned_processes` inside the image:

```python
parent = proc.parent()
if parent is None or parent.pid == 1:
    logging.warning(f"Found orphaned process: ...")
    proc.terminate()
```

It calls any Hue process whose parent is PID 1 an orphan. Without an init, the supervisor that started gunicorn *is* a child of PID 1, so gunicorn kills its own parent. `init: true` puts tini at PID 1, the predicate is false, and the same image comes up in about eight seconds.

**3. The first visitor becomes the administrator.** Hue makes the first account registered through its web UI a superuser. The admin hook seeds `nexus-hue-admin` with a generated password instead, and re-running it rotates that password rather than leaving a stale hash — so a credential rotation in Infisical converges.

### Behind the tunnel, Django needs telling

TLS terminates at the Cloudflare Tunnel, so Django only learns the real scheme from `X-Forwarded-Proto`. Without that it computes the expected CSRF origin as `http://hue.YOUR_DOMAIN` while the browser sends `https://…`, and **every POST is refused — the login included**. What the user meets is a bare "CSRF error" page; what Django logs is:

```
Forbidden (Origin checking failed - https://hue.example.com does not match
any trusted origins.): /hue/accounts/login
```

Two settings cover it, and either one alone is enough — verified separately:

| Setting | Effect |
|---|---|
| `secure_proxy_ssl_header=true` | `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`, so the computed origin becomes `https://` |
| `[[session]] trusted_origins=$HUE_DOMAIN` | Django's `CSRF_TRUSTED_ORIGINS`; Hue expands it into both the `http://` and `https://` forms |

Both are set so that a proxy which stops sending the header does not lock everybody out.

### Configuration is written, not mounted

Hue merges every `.ini` under its conf directory and `z-` sorts last, so the overrides file wins. It has to carry the database password and the secret key, though, and neither belongs in the repository — so the entrypoint renders it at container start from the `.env`.

One detail that costs a restart if you miss it: the shipped file is root-owned `0644` and the container runs as `hue`, which can *unlink* it (the conf directory is hue-owned) but cannot overwrite it in place. The entrypoint does `rm -f` first; without that the container exits on `cannot create .../z-hue-overrides.ini: Permission denied`.

### Which engines, and why only three

Only engines whose driver is actually in the image — checked with `pip list` rather than assumed:

| Interpreter | Driver present | Points at |
|---|---|---|
| PostgreSQL | `psycopg2-binary` | the shared `postgres` stack |
| Trino | `trino` | the `trino` stack |
| ClickHouse | `sqlalchemy-clickhouse` | the `clickhouse` stack |

Each entry is inert until the stack behind it is enabled; a missing host shows as a connection error in the editor, not a broken Hue.

HDFS, HBase, Oozie, Impala and Solr are blacklisted in the configuration. None of them is deployed here, and leaving their apps enabled puts permanently broken tabs in the navigation.

### Related

- [Trino](./trino.md), [ClickHouse](./clickhouse.md), [PostgreSQL](./postgres.md) — the engines behind the three interpreters
- [CloudBeaver](./cloudbeaver.md) — a lighter browser SQL client covering more drivers
- [Superset](./superset.md) — dashboards rather than an editor
