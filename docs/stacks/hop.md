---
title: "Apache Hop"
---

## Apache Hop

![Apache Hop](https://img.shields.io/badge/Apache_Hop-3A6EA5?logo=apache&logoColor=white)

**Visual ETL — pipelines and workflows built in the browser**

Apache Hop builds data integration visually. A *pipeline* transforms data row by row — read, filter, join, aggregate, write — and a *workflow* orchestrates jobs and pipelines with conditions and error paths. Everything is designed, run and debugged in the browser (Hop Web). Hop is the successor of Pentaho Data Integration (Kettle) and a gentle way into ETL before pipelines are written as code in [Mage](mage.md) or [Kestra](kestra.md).

| Setting | Value |
|---------|-------|
| Default Port | `8182` on the host (bound to `127.0.0.1`), `8080` in the container |
| Suggested Subdomain | `hop` |
| Entry point | `https://hop.<domain>/ui` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — see below |
| Persistence | The project, under `/mnt/nexus-data/hop`, backed up to R2 |
| Website | [hop.apache.org](https://hop.apache.org) |
| Source | [GitHub](https://github.com/apache/hop) |

### Authentication

Hop Web has **no login of its own**. Its documentation only describes adding Tomcat basic authentication by hand. Cloudflare Access is therefore the only gate, as for Lakekeeper or Temporal in this stack, and the repository's tests forbid ever making Hop public or giving it a firewall port.

The same web application also serves the Hop Server API under `/hop`, unauthenticated as well. It sits behind the same Access policy; inside the server, any container on `app-network` can reach it at `http://hop:8080/hop`.

### Connecting to data

The bundled JDBC drivers include PostgreSQL, SQLite, H2 and others, so a database connection to `postgres:5432` (or any database on `app-network`) works straight away. Database passwords are in Infisical.

### Persistence

Hop works in the project `nexus`, whose folder is `/project`, bind-mounted from `/mnt/nexus-data/hop` (owned by the image's user, `501:501`). The image registers the project from `HOP_PROJECT_NAME` / `HOP_PROJECT_FOLDER` on every start, so pipelines, workflows and project metadata all live in that folder and nothing worth keeping stays in the container. The rebuild teardown stops Hop and copies the folder to R2.

Unsaved work is not kept: Hop Web loses an open, unsaved pipeline when its session times out. Save often.

### Memory

`HOP_OPTIONS` sets the heap to 256 MB initial and 768 MB maximum, replacing the image's `-XX:+AggressiveHeap`, which sizes the heap from all the memory the JVM can see. Container limit: 1.5 GB.

### Health

`GET /ui` with curl, inside the container.
