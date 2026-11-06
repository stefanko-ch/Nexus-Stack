---
title: "Valkey"
---

## Valkey

![Valkey](https://img.shields.io/badge/Valkey-6983FF?logoColor=white)

**Redis-compatible in-memory data store**

Valkey is the open-source fork of Redis, maintained under the Linux Foundation and wire-compatible with it, so every Redis client and `redis-cli` command works. Keys, hashes, lists, sorted sets, pub/sub and streams make it the usual choice for:
- caching;
- rate limits;
- job queues;
- lightweight event streams.

| Setting | Value |
|---------|-------|
| Address | `valkey:6379`, inside `app-network` only |
| Public Access | None — internal only |
| Credentials | Default user, password generated per deployment (Infisical folder `valkey`) |
| Memory | `maxmemory 384mb`, `noeviction`; container limit 512 MB |
| Persistence | Append-only file in the Docker volume `valkey-data` |
| Website | [valkey.io](https://valkey.io) |
| Source | [GitHub](https://github.com/valkey-io/valkey) |

### Connecting

From a notebook on `app-network`, with the standard Redis client:

```python
import redis

r = redis.Redis(host="valkey", port=6379, password="<VALKEY_PASSWORD>")
r.set("greeting", "hello")
r.get("greeting")
```

From the server:

```bash
ssh nexus 'docker exec -it valkey sh -c "REDISCLI_AUTH=\"\$VALKEY_PASSWORD\" valkey-cli"'
```

### Password

The password goes into the config file `/tmp/valkey.conf` when the container starts, with mode `600` and owned by `valkey`. It is not on the command line, so `docker inspect` and `ps` do not show it. The deploy refuses to start Valkey without a password, because every container on `app-network` could otherwise read and write it.

### Memory

`maxmemory` is 384 MB with `noeviction`. A full store answers writes with an error instead of silently dropping keys, the safer default for a store that might hold queues. For a pure cache, `CONFIG SET maxmemory-policy allkeys-lru` changes that at runtime.

### Persistence

Data is written to an append-only file in the `valkey-data` volume.

- **`rebuild` (default): the data does not survive a teardown.** Valkey is not in the R2 backup list.
- **`snapshot`: the data survives**, because the whole disk is imaged.
