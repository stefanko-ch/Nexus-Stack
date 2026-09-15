---
title: "Neo4j"
---

## Neo4j

![Neo4j](https://img.shields.io/badge/Neo4j-4581C3?logo=neo4j&logoColor=white)

**Graph database with the Cypher query language**

Neo4j stores data as nodes and relationships, each carrying properties, and queries it with Cypher — a pattern-matching language that reads like the graph it describes. Questions that are a chain of self-joins in SQL (friends of friends, shortest paths, who is connected to a fraud ring) are one `MATCH` here. Features include:

- Neo4j Browser for running Cypher and exploring results as a graph
- Cypher, including shortest-path and variable-length pattern matching
- ACID transactions on a native graph store
- Bolt drivers for Python, Java, JavaScript, Go and .NET
- A Query API over HTTP for clients without a Bolt driver

This is **Community Edition**, single instance: one database (`neo4j`) plus the `system` database, no roles or fine-grained privileges, no clustering.

| Setting | Value |
|---------|-------|
| Host Port | `7474` — the tunnel's origin, served by `neo4j-proxy` (see [How Browser reaches Bolt](#how-browser-reaches-bolt)) |
| Bolt | `neo4j:7687` inside `app-network`; `127.0.0.1:7687` on the server |
| Suggested Subdomain | `neo4j` |
| Public Access | No (protected by Cloudflare Access) |
| Admin Username | `nexus-neo4j` |
| Admin Password | Generated per deployment — in Infisical under `neo4j` |
| Memory | 1 GiB heap, 512 MiB page cache, 2 GiB container limit |
| Persistence | Local Docker volume (compose key `neo4j_data`) — see [What survives a teardown](#what-survives-a-teardown) |
| Website | [neo4j.com](https://neo4j.com) |
| Source | [GitHub](https://github.com/neo4j/neo4j) |

### Using Neo4j Browser

1. Enable **Neo4j** in the Control Plane → Spin Up.
2. Open `https://neo4j.YOUR_DOMAIN` → Cloudflare Access email OTP → Neo4j Browser.
3. In the connect form, set the connection URL to **`bolt+s://neo4j.YOUR_DOMAIN:443`**, user `nexus-neo4j`, and the password from Infisical.

The form pre-fills something else, and it will not connect. Neo4j fills it from its discovery document, which names the Bolt port `7687` — a port the tunnel does not carry. Use `443`, the port the page itself came from, and `bolt+s`: the page is HTTPS, so the WebSocket has to be encrypted too. `bolt+s` rather than `neo4j+s` because it connects directly, with no routing-table round trip.

To skip retyping, open the Browser with the URL already set:

```
https://neo4j.YOUR_DOMAIN/browser/?dbms=bolt%2Bs://neo4j.YOUR_DOMAIN:443
```

The `dbms` parameter was verified to pre-fill the protocol and host in the pinned version.

### How Browser reaches Bolt

Neo4j Browser is a web page served by the HTTP port, but it does not run queries over that port. It opens a **Bolt** connection from your own browser, over WebSocket, to the Bolt port. Through Cloudflare Tunnel only one origin sits behind `neo4j.YOUR_DOMAIN`, so on its own the page would load and then have nowhere to connect.

The stack solves that inside itself rather than with a second public hostname. `neo4j-proxy` (nginx) is the tunnel's origin and splits on the `Upgrade` header:

| Request | Goes to |
|---|---|
| `Upgrade: websocket` | `neo4j:7687` — Bolt accepts WebSocket on its own port |
| anything else | `neo4j:7474` — Browser, discovery, Query API |

Measured against `neo4j:2026.08.1-community`: a Bolt handshake over WebSocket to `7687` negotiates Bolt 5.8; the same handshake to `7474` gets a plain HTTP 200 and no upgrade. With the proxy in front, the real Neo4j Browser connected to `bolt://127.0.0.1:7474` and returned `RETURN 6 * 7` → `42`.

**What was not tested locally:** the encrypted half. Locally the page was plain HTTP and the socket plain `ws://`; through the tunnel Cloudflare terminates TLS and forwards the upgrade to the proxy. The WebSocket is same-origin with the page, so the Access cookie travels with it — the same property Wetty and Jupyter kernels already rely on behind Access — but the first spin-up is the first end-to-end run of this path.

No OpenTofu change was needed: the tunnel still maps one subdomain to one local port, as for every other stack.

### Connecting from other stacks

From Jupyter, Marimo, Kestra or anything else on `app-network`:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("nexus-neo4j", password))
records, _, _ = driver.execute_query("MATCH (n) RETURN count(n) AS nodes")
```

Both `bolt://neo4j:7687` and `neo4j://neo4j:7687` were verified with the Python driver from a separate container. Plain Bolt, no TLS, inside the Docker network — the encryption boundary is the tunnel, as for PostgreSQL and every other stack here. The `neo4j` Python package is not preinstalled in the notebook images; `pip install neo4j` first.

### Connecting from your machine

Bolt is published on the server's loopback only, so forward it over SSH (see [SSH Access](../admin-guides/ssh-access.md)):

```bash
ssh -L 7687:127.0.0.1:7687 nexus
```

Then point a local driver, `cypher-shell` or Neo4j Desktop at `bolt://localhost:7687`. This is ordinary SSH port forwarding; nothing in the repository disables it, but it has not been exercised against a deployed server.

There is deliberately no `tcp_ports` entry. Opening Bolt through the Hetzner firewall would put an unencrypted password login on the public internet, and nothing in the stack needs it.

### The `nexus-neo4j` account

The image can only seed a user called `neo4j`, which is the guessable default the `nexus-` naming rule exists to prevent. Community Edition cannot rename or suspend a user — `ALTER USER neo4j SET STATUS SUSPENDED` is refused with *"'SET STATUS' is not supported in community edition"* — but it can create one user and drop another. So:

1. On first start the image seeds `neo4j` from `NEO4J_AUTH`, with the generated password.
2. The admin-setup hook (`render_neo4j_hook` in `src/nexus_deploy/services.py`) signs in as `neo4j`, creates `nexus-neo4j` with the same password, then signs in as `nexus-neo4j` and drops `neo4j`. If the create fails, it tries `nexus-neo4j` once more before reporting `failed` — two spin-ups can run at once (#801), and the second then finds `neo4j` already dropped by the first.
3. On every later spin-up the hook finds that `nexus-neo4j` already signs in, and repeats only the `DROP USER neo4j IF EXISTS`.

Verified against the pinned image: a fresh database ends `configured` with `nexus-neo4j` as the only user, a second run ends `already-configured`, and after a restart `neo4j` stays dropped — `NEO4J_AUTH` only seeds an empty database. Between the container starting and the hook running, `neo4j` exists with the generated password; there is no window with a default password.

Community Edition has no roles, so every user is effectively an administrator. There is one account, and it is this one.

### Credentials

```
Infisical → neo4j → NEO4J_USERNAME   nexus-neo4j
                    NEO4J_PASSWORD   (generated)
```

The password is generated by `random_password.neo4j_admin` with `special = false`. That is load-bearing, not cosmetic: the hook places the password inside a Cypher string literal, and `service_env._render_neo4j` refuses to render anything but letters and digits.

On the server the password is in `stacks/neo4j/.env` as `NEXUS_NEO4J_PASSWORD`. Not `NEO4J_PASSWORD`: the image turns every `NEO4J_*` variable into a config setting and refuses to start on an unknown one — measured: *"Unrecognized setting. No declared setting with name: PASSWORD"*.

Like every credential in this project, it is also synced into Kestra as a `SECRET_*` variable (#716 tracks narrowing that).

### What survives a teardown

Data lives in the Docker volume `neo4j_data`. Neo4j is not among the stacks `s3_restore.standard_targets()` backs up, so:

- **`rebuild` lifecycle:** the graph is **gone** after a teardown. The next spin-up starts an empty database, with a newly generated password, and the hook sets up `nexus-neo4j` again.
- **`snapshot` lifecycle:** the volume is on the root disk, which is imaged, so the graph survives — and so does the OpenTofu state, so the password does not change.

If a graph matters on a `rebuild` stack, export it before the teardown, or keep the script that loads it so the next spin-up can rebuild it.

### Troubleshooting

**The hook reports `failed`: "could not sign in as nexus-neo4j, and could not create it as neo4j either".** The database holds a different password than the container was given. Neither lifecycle produces that on its own — in `rebuild` mode the volume goes with the password, in `snapshot` mode neither changes — so it follows a `random_password` being replaced while the volume survived. `NEO4J_AUTH` does not help: it only seeds an empty database.

To align the database with the current password while keeping the data, start the volume once with authentication off and set the password from there:

```bash
ssh nexus
docker stop neo4j
docker run -d --rm --name neo4j-recover -v neo4j_neo4j_data:/data \
  -e NEO4J_dbms_security_auth__enabled=false neo4j:2026.08.1-community
# wait until `docker exec neo4j-recover wget -q -O /dev/null http://localhost:7474/` succeeds, then:
PW=$(sed -n 's/^NEXUS_NEO4J_PASSWORD=//p' /opt/docker-server/stacks/neo4j/.env)
printf 'ALTER USER `nexus-neo4j` SET PLAINTEXT PASSWORD "%s" CHANGE NOT REQUIRED;\n' "$PW" \
  | docker exec -i neo4j-recover cypher-shell -d system
unset PW
docker stop neo4j-recover
docker start neo4j
```

The same sequence was run locally against a volume whose password had diverged: the `ALTER USER` succeeded and a node written before the divergence was still readable with the new password. The volume name assumes the compose project is named after the stack directory, which is how `compose_runner` starts it (`cd stacks/neo4j && docker compose up`); check with `docker volume ls` if it differs. If the data does not matter, removing the volume and re-running spin-up is simpler.

**Browser loads but will not connect.** Check the connection URL first: `bolt+s://neo4j.YOUR_DOMAIN:443`, not the pre-filled `:7687`. Then check the proxy is healthy (`docker ps --filter name=neo4j-proxy`) — it only starts once `neo4j` itself is healthy.

**Quick check from the server:**

```bash
ssh nexus "curl -s http://127.0.0.1:7474/" | jq '.neo4j_version, .neo4j_edition'
```

This goes through the proxy, and answers without credentials.
