---
title: "DragonflyDB"
---

## DragonflyDB

![DragonflyDB](https://img.shields.io/badge/DragonflyDB-0D1117?logo=redis&logoColor=white)

**Redis-compatible in-memory data store**

DragonflyDB answers the Redis and Memcached APIs with a multi-threaded engine. Redis clients, commands and data types work unchanged, so next to [Valkey](valkey.md) it compares engines rather than APIs.

| Setting | Value |
|---------|-------|
| In-cluster | `redis://dragonfly:6379` |
| Credentials | `nexus-dragonfly`, password generated per deployment (Infisical folder `dragonfly`) |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `dragonfly-data` (snapshot written on shutdown) |
| Licence | Business Source License 1.1 — not an OSI licence |
| Website | [dragonflydb.io](https://www.dragonflydb.io) |

### First steps

From a notebook or any container on `app-network`:

```python
import redis

r = redis.Redis(host="dragonfly", port=6379, username="nexus-dragonfly", password="<DRAGONFLY_PASSWORD>")
r.set("greeting", "hello")
r.get("greeting")  # b'hello'
```

From the server, `redis-cli` reads the password from `REDISCLI_AUTH`. The container already has it as `DRAGONFLY_PASSWORD`, so it never has to be typed or passed on a command line:

```bash
docker exec -it dragonfly sh -c 'REDISCLI_AUTH="$DRAGONFLY_PASSWORD" exec redis-cli --user nexus-dragonfly'
```

### Authentication

The stack writes an ACL file on every start, from the generated password. It has two users:

- `nexus-dragonfly` with full rights.
- `default` switched off, so a client that sends no credentials gets `NOAUTH Authentication required`.

Dragonfly rejects the whole ACL file for a `default OFF` line without a password, and then runs with an open `default` user. So `default` gets a random throwaway password on each start, which is stored nowhere else. The healthcheck logs in as `nexus-dragonfly` and checks `ACL WHOAMI`, so a broken ACL file shows up as an unhealthy container rather than an open one.

Tested: login, wrong password and no password refused, data kept across a restart.

### Resources

Dragonfly refuses to start unless its memory limit is at least 256 MB per thread, and it starts one thread per CPU by default. The stack sets 2 threads and `maxmemory` 1 GB, inside a 1.5 GB container limit. It used about 15 MB when idle.

The daily version check, which also reports uptime and hardware details, is off.

### Persistence

Dragonfly writes a snapshot of the dataset to `dragonfly-data` when it shuts down, and loads it on start.

- **`rebuild` (default): it does not survive a teardown.** Dragonfly is not in the R2 backup list.
- **`snapshot`: it survives**, because the whole disk is imaged.

### Licence

Dragonfly is under the Business Source License 1.1. It allows this kind of use, including teaching and internal use. It forbids offering Dragonfly as a hosted service in competition with Dragonfly's own. Each release converts to Apache 2.0 four years after its date.
