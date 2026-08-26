---
title: "Setup: dlt environment and Postgres credentials"
description: "Create an isolated Python environment with uv, install dlt, and wire up your Nexus Postgres credentials"
order: 1
---

# Setup: dlt environment and Postgres credentials

Before writing any pipeline, you need a working Python environment inside code-server and a credentials file that tells dlt how to reach the Nexus Postgres database. This page covers both — it takes about 5 minutes and you only do it once.

## Prerequisites

- Nexus-Stack deployment with `code-server` and `postgres` enabled
- Familiarity with opening a terminal in code-server — see [Run curl in the code-server terminal](/docs/tutorials/code-server/terminal-curl/) if this is your first time

## 1. Create a working directory

All dlt tutorials live inside your workspace repo so your scripts survive container restarts and teardowns. Open a terminal in code-server and run:

```bash
cd ~/nexus-<your-domain>-workspace
mkdir dlt && cd dlt
```

Replace `nexus-<your-domain>-workspace` with your actual repo name — it follows the pattern `nexus-<domain-with-hyphens>-workspace`. For a domain `odeslab.com` it would be `nexus-odeslab-com-workspace`.

## 2. Create a virtual environment

```bash
uv venv .venv
source .venv/bin/activate
```

Your prompt now shows `(.venv)`. The environment is isolated — packages installed here don't affect anything else on the server.

## 3. Install dlt with the Postgres plugin

```bash
uv pip install "dlt[postgres]"
```

This installs dlt and `psycopg2-binary`, the driver dlt uses to talk to Postgres. Verify:

```bash
dlt --version
```

Expected output: `dlt version 1.x.x` (exact version may vary).

## 4. Configure Postgres credentials

dlt reads credentials from a file called `secrets.toml` inside a `.dlt/` directory next to your scripts.

```bash
mkdir .dlt
```

Open the **Secrets** page in your Control Plane, expand the `postgres` entry, and copy the value of `POSTGRES_PASSWORD`. Then create the file:

```bash
cat > .dlt/secrets.toml << 'EOF'
[destination.postgres.credentials]
host = "postgres"
port = 5432
database = "postgres"
username = "nexus-postgres"
password = "YOUR_POSTGRES_PASSWORD"
EOF
```

Replace `YOUR_POSTGRES_PASSWORD` with the value you copied from Infisical.

The host `postgres` is the Docker service name — it resolves inside the server's network and is only reachable from code-server, not from your laptop.

## 5. Protect your credentials

`secrets.toml` contains your database password. Add it to `.gitignore` so it's never committed to your workspace repo:

```bash
grep -qxF '.dlt/secrets.toml' .gitignore 2>/dev/null || echo '.dlt/secrets.toml' >> .gitignore
```

## What's next

Your environment is ready. The next tutorial builds your first pipeline: [Wikipedia pageviews → Postgres](./wikipedia-pipeline.md) — a single resource, a single table, and a first look at how dlt handles schema inference automatically.
