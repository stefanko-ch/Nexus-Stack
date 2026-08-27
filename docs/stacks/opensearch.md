---
title: "OpenSearch"
description: "Apache-2.0 search and analytics engine with Dashboards, speaking the Elasticsearch API"
---

# OpenSearch

![OpenSearch](https://img.shields.io/badge/OpenSearch-005EB8?logo=opensearch&logoColor=white)

OpenSearch is the Apache-2.0 fork of Elasticsearch 7.10, shipped here with
its Dashboards UI. It speaks the Elasticsearch REST API, so anything
written against that API works unchanged — `opensearch-py`,
`elasticsearch-py`, Logstash, Fluent Bit.

Build an index from a notebook, query it with the DSL, then explore and
visualise it in Dashboards without leaving the stack.

## Configuration

| Setting | Value |
|---|---|
| Subdomain | `opensearch.<your-domain>` (Dashboards) |
| Host port | `5601` → container `5601` |
| API | `http://opensearch:9200` — internal only, on `app-network` |
| Public | No — Cloudflare Access (email OTP) |
| Data | Named volume `opensearch-data`, survives a restart |

### Containers

| Container | Role |
|---|---|
| `opensearch` | The node. REST API on 9200, security plugin on, single-node discovery. |
| `opensearch-dashboards` | The UI. The only published port; the browser never contacts the node directly. |

## Not shared with Marquez

[Marquez](./marquez.md) ships its own `marquez-opensearch` inside its own
stack and does **not** use this one. That is deliberate: sharing would mean
Marquez's lineage search breaks the moment somebody disables OpenSearch
here, which is exactly what the project's "each stack brings its own
resources" rule exists to prevent.

The cost is about 1 GB of RAM twice over. The benefit is that either stack
can be switched off without touching the other.

## Credentials

Both values are in Infisical under the `opensearch` folder:
`OPENSEARCH_USERNAME` (which is `admin`) and `OPENSEARCH_ADMIN_PASSWORD`.

You do not need it for Dashboards — Cloudflare Access already
authenticated whoever reached the page, so the Dashboards login screen is
turned off. You **do** need it for the API, which keeps authentication
because notebooks and pipelines inside the stack reach it directly and a
credential-free index stops being sensible the moment more than one person
uses it.

This is one of the few passwords in the project generated with special
characters at all. OpenSearch has
validated `OPENSEARCH_INITIAL_ADMIN_PASSWORD` since 2.12 and refuses to
start without one. The generator is restricted to `-`, `_` and `.` so the
value stays inert in a shell, a compose `.env` parser and a YAML scalar —
which is why every other password in the project avoids specials entirely.

### Why the username is `admin` and not `nexus-opensearch`

This is a deliberate exception to the project's rule that service accounts
carry a `nexus-` prefix, and it is worth stating rather than leaving to be
noticed.

The name is a compiled constant in OpenSearch's security plugin — its demo
configurator declares `static String ADMIN_USERNAME = "admin"` and offers
no environment override. `OPENSEARCH_INITIAL_ADMIN_PASSWORD` replaces the
*password* inside `internal_users.yml` and nothing else. Renaming the
account means shipping our own `internal_users.yml` containing a bcrypt
hash generated at deploy time, then running `securityadmin.sh` to load it.

The rule exists to stop default-username guessing, and that threat needs a
reachable endpoint. This one has no published host port and no `tcp_ports`
entry, so it answers only inside `app-network`, and the password is 24
random characters. The same exception applies to the OpenSearch inside the
[Marquez](./marquez.md) stack.

If the prefixed account is wanted anyway, the work is a custom security
configuration and a `services-configure` hook to apply it — a change worth
its own issue rather than a footnote here.

## Using it from the stack

From Jupyter, Marimo or code-server, with the password pulled from the
environment rather than pasted into a notebook:

```python
import os
from opensearchpy import OpenSearch

client = OpenSearch(
    hosts=[{"host": "opensearch", "port": 9200}],
    http_auth=("admin", os.environ["OPENSEARCH_ADMIN_PASSWORD"]),
    use_ssl=False,
)

client.index(index="orders", body={"id": 1, "total": 42.5})
client.indices.refresh(index="orders")
print(client.search(index="orders", body={"query": {"match_all": {}}}))
```

The index appears in Dashboards under **Discover** once you create an index
pattern for it.

## Deliberate limitations

**No published API port.** Zero open ports is the project's baseline, so
only Dashboards is reachable from outside. In-stack clients use
`http://opensearch:9200` over `app-network`. If an external client
genuinely needs the API, add a `tcp_ports` entry in `services.yaml` rather
than a `ports:` line in the compose file — that way the firewall rule is
managed and reset on teardown like every other one.

**TLS is off on the HTTP layer.** The port is not published and the traffic
stays inside Docker; leaving TLS on would force every in-stack client to
trust the bundled demo certificate, which is a worse trade than terminating
TLS at Cloudflare as the rest of the stack does. Authentication stays on.

**Single node.** `discovery.type=single-node`, so there is no replication
and a cluster health of `yellow` is normal — unassigned replica shards have
nowhere to go. That is expected, not a fault.

**Dashboards must match the node's version.** Both are pinned to 2.19.6.
Dashboards refuses to start against an OpenSearch of a different minor and
says so in its log; bump the two together.

## Debugging

```bash
# Is the node up? A 401 is a healthy answer here — it means the security
# plugin is loaded and asking for credentials.
ssh nexus "docker exec opensearch curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9200/"

# Cluster health (yellow is normal on a single node).
# The password is expanded INSIDE the container by `sh -c`. It lives in
# that container's environment, not in the host shell, so expanding it on
# the ssh line would send an empty one. Note the container's variable is
# OPENSEARCH_INITIAL_ADMIN_PASSWORD, not OPENSEARCH_ADMIN_PASSWORD.
ssh nexus "docker exec opensearch sh -c 'curl -s -u admin:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD http://localhost:9200/_cluster/health?pretty'"

# Did Dashboards reach the node?
ssh nexus "docker logs opensearch-dashboards 2>&1 | grep -iE 'unable to connect|license|Server running'"

# Memory: OpenSearch is JVM-heavy and exit 137 means it was OOM-killed
ssh nexus "docker inspect opensearch --format '{{.State.ExitCode}} {{.RestartCount}}'"
```

A Dashboards page that loads but shows "OpenSearch Dashboards server is not
ready yet" usually means the node is still starting — it has a 90-second
`start_period` for exactly that reason.

## Related

- [Marquez](./marquez.md) — runs its own separate OpenSearch for lineage search
- [Meilisearch](./meilisearch.md) — much lighter, for straightforward full-text search where the Elasticsearch API is not the point
- [Quickwit](./quickwit.md) — search built for logs and traces on object storage
- [OpenSearch documentation](https://opensearch.org/docs/latest/)
