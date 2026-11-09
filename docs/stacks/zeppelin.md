---
title: "Apache Zeppelin"
---

## Apache Zeppelin

![Zeppelin](https://img.shields.io/badge/Apache_Zeppelin-1D4E89?logo=apache&logoColor=white)

**Web notebooks with many interpreters**

In Zeppelin, every paragraph of a notebook names its interpreter: `%python`, `%jdbc`, `%sh`, `%md`, `%sparql` and others. Tables and charts are built in.

| Setting | Value |
|---------|-------|
| Default Port | `8125` (bound to `127.0.0.1` on the host; container port 8080) |
| Suggested Subdomain | `zeppelin` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | `nexus-admin`, password generated per deployment (Infisical folder `zeppelin`) |
| Persistence | Docker volume `zeppelin-notebooks` |
| Website | [zeppelin.apache.org](https://zeppelin.apache.org) |

### Zeppelin next to Jupyter and marimo

[Jupyter](jupyter.md) and [marimo](marimo.md) are Python notebooks. Zeppelin mixes languages in one notebook. A `%jdbc` paragraph can query [Postgres](postgres.md) or [Trino](trino.md), and a `%python` paragraph can process the result or query [Jena Fuseki](jena-fuseki.md) with `requests`. The `%sparql` interpreter cannot reach Fuseki: it has no setting for credentials, and Fuseki requires a login. [jena-fuseki.md](jena-fuseki.md) has the `%python` example.

### Login

Sign in as `nexus-admin` with `ZEPPELIN_PASSWORD` from Infisical.

The stack writes `shiro.ini` on every start. Without it, Zeppelin lets anyone in as `anonymous`, and the `%sh` interpreter runs any command in the container.

### First steps

Create a note and run:

```text
%python
import pandas as pd
df = pd.DataFrame({"x": range(5), "y": [v * v for v in range(5)]})
z.show(df)
```

`z.show` renders the DataFrame as Zeppelin's table, with the chart buttons above it. Running a `%python` paragraph through the API was tested. The snippet above was not.

The volume starts with Zeppelin's tutorial notebooks. The Spark and Flink tutorials need a Spark or Flink installation the image does not contain, so they do not run as shipped. Connecting Zeppelin to the [Spark](spark.md) stack was not tried.

### Persistence

Notebooks are in `zeppelin-notebooks`. Interpreter settings changed in the UI are stored in `conf/` inside the container, and are lost when the container is recreated.

- **`rebuild` (default): notebooks do not survive a teardown.** Zeppelin is not in the R2 backup list. Export notes (JSON or `.zpln`) to keep them, or keep them in [Forgejo](forgejo.md).
- **`snapshot`: they survive**, because the whole disk is imaged.
