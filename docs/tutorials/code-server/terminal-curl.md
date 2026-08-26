---
title: "Run curl in the code-server terminal"
description: "Open a terminal inside code-server and reach internal Nexus-Stack services by their Docker hostnames"
order: 1
---

# Run curl in the code-server terminal

Most admin APIs inside Nexus-Stack (Redpanda, Redpanda Connect, Flink JobManager) are **only reachable from within the server's Docker network** — they're not exposed to the public internet. The simplest way to hit them is from a terminal inside **code-server**, which runs on the same network.

## Prerequisites

- Nexus-Stack deployment with `code-server` enabled in the Control Plane → [Stacks](/docs/guides/user-guides/stacks/) page

## Open code-server

Go to `https://code.<your-domain>` in your browser. First visit: Cloudflare Access sends an email OTP, enter the code.

You land in a familiar VS Code interface — same shortcuts, same extensions, same everything. It's running on your Nexus-Stack server, not your laptop.

## Open a terminal

Three equivalent ways:

- **Keyboard:** `` Ctrl+` `` (backtick) — same on Windows, Linux, and macOS
- **Menu:** **Terminal → New Terminal**
- **Command palette:** `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS) → type "terminal: create"

The terminal opens at the bottom of the window. Default shell is `bash`, default working directory is your home (`/home/coder` or similar).

## Your first curl

Try pinging Redpanda's admin API:

```bash
curl -s http://redpanda:9644/v1/status/ready
```

Expected output (whitespace-prettified):

```json
{"status":"ready"}
```

That's it — you've just hit a service by its **Docker service name** (`redpanda`), which resolves inside the network because Docker Compose sets up internal DNS for every service.

## Internal hostnames you'll actually use

| Hostname | Port | What it is | Use for |
|---|---|---|---|
| `redpanda` | `9092` | Kafka-compatible broker | Kafka clients (producer/consumer bootstrap) |
| `redpanda` | `9644` | Redpanda admin API | Cluster config, topic metadata |
| `redpanda-connect` | `4195` | Redpanda Connect REST API | Stream lifecycle (deploy, list, delete) |
| `flink-jobmanager` | `8081` | Flink JobManager REST API | Register in Dinky, query job state |
| `forgejo` | `3000` | Forgejo Git server | Git operations when Forgejo stack is enabled |
| `infisical` | `8080` | Infisical API | Secrets read/write from code |

These hostnames **only resolve inside the Docker network**. They will not work from your laptop. They will work from code-server, and from any Docker container running alongside the services.

## Common patterns

**Check if a service is reachable at all:**
```bash
curl -sI http://redpanda-connect:4195/ready
```
`-I` sends a HEAD request, `-s` silences progress output. A `200 OK` in the response means the service is up.

**POST a JSON payload:**
```bash
curl -s -X POST http://host:port/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

**POST a file as the body (e.g. YAML for Redpanda Connect):**
```bash
curl -s -X POST http://redpanda-connect:4195/streams/demo \
  -H "Content-Type: application/yaml" \
  --data-binary @pipeline.yaml
```
Note the `@` — that tells curl to read the body from a file.

**Pretty-print a JSON response:**
```bash
curl -s http://redpanda-connect:4195/streams | python3 -m json.tool
```
`python3` is preinstalled on the server — this is the fastest way to make JSON readable without installing `jq`.

## Why not just run curl on my laptop?

Because only a handful of services are exposed to the public internet — the ones with a subdomain (`redpanda-console.<domain>`, `code.<domain>`, `dinky.<domain>`). Those are routed through the Cloudflare Tunnel. The admin APIs (`:9644`, `:4195`, `:8081`) stay inside the network on purpose: they'd be a massive attack surface if exposed.

Code-server is the escape hatch: you're inside the network, with a terminal, authenticated by Cloudflare Access.

## Next steps

- [Set up an isolated Python environment](/docs/tutorials/code-server/python-uv/) — when you need to run Python scripts
- [Enable auto-create topics via Redpanda's admin API](/docs/tutorials/redpanda/auto-create-topics/) — common operation, single curl call
