---
title: "Apache Cassandra"
---

## Apache Cassandra

![Cassandra](https://img.shields.io/badge/Apache_Cassandra-1287B1?logo=apachecassandra&logoColor=white)

**The data model, without the cluster**

Cassandra stores wide rows partitioned across a ring, and its design forces the table to follow the query rather than the other way round.

| Setting | Value |
|---------|-------|
| Host Port | `9042` (CQL native protocol) |
| Web UI | none — CQL only |
| Public Access | No (internal-only; a Hetzner firewall rule opens 9042 for external clients) |
| Website | [cassandra.apache.org](https://cassandra.apache.org) |
| Image | `cassandra:5.0.6` |
| Credentials | `nexus-cassandra` / Infisical `/cassandra/CASSANDRA_PASSWORD` |

### One node, on purpose

Cassandra's reason to exist is horizontal scale across many machines, and there is one machine here. What a single node still gives you is everything about the *model*: partition keys, clustering columns, a table per access pattern, and the consequences of choosing them badly. That is what this stack is for.

```sql
CREATE KEYSPACE demo WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
CREATE TABLE demo.sales (region text, ts timeuuid, amount int, PRIMARY KEY (region, ts));
```

### Authentication is off in the image

The official image's entrypoint substitutes exactly eight keys into `cassandra.yaml` — `cluster_name`, `seeds`, `listen_address` and five more — and `authenticator` is not among them. The stock value is `AllowAllAuthenticator`, so **an unmodified container accepts any client with no credentials at all**.

This stack's entrypoint rewrites `authenticator` and `authorizer` before handing over, and the admin hook then does what the image cannot: it creates `nexus-cassandra` with the generated password and drops the built-in `cassandra` superuser, whose password is `cassandra`. Afterwards:

```
cqlsh -u cassandra -p cassandra
  → Provided username cassandra and/or password are incorrect
```

The hook is idempotent — a second run reports `already-configured`.

It waits for an account that can *sign in*, not for the port. `CassandraRoleManager` creates the default superuser on a background task **70 seconds after the native transport opens** — measured on a fresh node, with `nodetool statusbinary` already reporting `running`. A hook keyed on the port alone runs while the only account it could use does not exist yet, and every statement fails. The same caveat applies to the container healthcheck below: healthy means the port answers, not that the database has an account.

### It is one of the heaviest stacks here

`mem_limit` is 3 GB, and that number is measured rather than chosen. At 2 GB the container is OOM-killed during startup (exit 137, `OOMKilled=true`) even with a 1 GB heap: `AlwaysPreTouch` commits the whole heap immediately and the direct-memory pool sits beside it. A started node settles at about 2.4 GiB RSS.

Two JVM sizes are set explicitly because Cassandra derives both from `/proc/meminfo`, which reports the **host's** memory rather than the container's limit:

| Variable | Value | Without it |
|---|---|---|
| `MAX_HEAP_SIZE` | `1G` | a quarter of the whole server |
| `JVM_EXTRA_OPTS` → `MaxDirectMemorySize` | `512M` | asked for 4009M |

Enable this stack when you want it, not by default.

### Two things that look tidier and break

**`CASSANDRA_SEEDS: "cassandra"`.** Naming the container as its own seed does not start:

```
WARN  SimpleSeedProvider - Seed provider couldn't lookup host cassandra
Exception ... The seed provider lists no seeds.
```

The lookup happens before the node is reachable under that name. The image's default — the node's own broadcast address — is the correct seed for a single node, so the variable is deliberately not set.

**`nodetool status` as a healthcheck.** It reports `UN` (Up/Normal) while the CQL port is still refusing connections — measured at 50s versus 60s on a fresh node. A stack depending on that healthcheck would start against a closed port. The probe here is `nodetool statusbinary`, which prints `running` only once the native transport is accepting.

### Connecting

From anywhere on `app-network`:

```bash
ssh nexus
docker exec -it cassandra sh -c 'cqlsh -u nexus-cassandra -p "$NEXUS_CASSANDRA_PASSWORD"'
```

The single quotes around the whole `sh -c` argument are what make that work: `NEXUS_CASSANDRA_PASSWORD` lives in the **container's** environment, so it has to be expanded there. Written with double quotes it expands on the server instead, where it is unset, and `cqlsh` is handed an empty password.

From outside, the firewall rule on port 9042 lets DBeaver, CloudBeaver or any driver connect with the same credentials — they are in Infisical under `/cassandra`.

### Related

- [CloudBeaver](./cloudbeaver.md) — a browser SQL client that speaks CQL
- [PostgreSQL](./postgres.md) — the other end of the design spectrum: one table, many queries
- [MongoDB](./mongodb.md) — the other non-relational store here, with its own firewall rule
