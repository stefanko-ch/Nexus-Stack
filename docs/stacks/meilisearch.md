---
title: "Meilisearch"
---

## Meilisearch

![Meilisearch](https://img.shields.io/badge/Meilisearch-FF5CAA?logo=meilisearch&logoColor=white)

**Lightning-fast Rust-based full-text search engine**

Meilisearch is a single-binary search engine written in Rust. Schema-less, sub-100ms typo-tolerant search, faceting, geo, and highlighting. Think "Algolia you self-host" — drop documents in via REST, query with prefix matching, get ranked results in milliseconds.

| Setting | Value |
|---------|-------|
| Default Port | `7700` |
| Suggested Subdomain | `meilisearch` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [meilisearch.com](https://www.meilisearch.com) |
| Source | [GitHub](https://github.com/meilisearch/meilisearch) |
| Docker image | [`getmeili/meilisearch`](https://hub.docker.com/r/getmeili/meilisearch) |

### Usage

1. Enable **Meilisearch** in the Control Plane → Spin Up
2. Get the master key from **Infisical** → folder `meilisearch` → key `MEILISEARCH_MASTER_KEY`
3. Hit the REST API with that key. The compose file sets `MEILI_ENV=production`, which intentionally disables the built-in `/` preview dashboard for security.

> **No web UI by design.** Clicking the Meilisearch tile in the Control Plane opens an **API-info modal** with the curl snippets and the Infisical-fetch command (it does **not** open the raw URL, which would just return `{"status":"Meilisearch is running"}`). The modal is wired up via the `api_only: true` flag in `services.yaml` — the same pattern is available for any future API-only service. If you genuinely want to see the raw JSON, the modal has an "Open raw API ↗" link.

   - **From inside Nexus-Stack** (other containers like code-server, Kestra, Dify): hit `http://meilisearch:7700/...` directly — internal Docker network, no CF Access in the path, just the master key as the auth layer.
   - **From outside** (your laptop, external CI): the `https://meilisearch.YOUR_DOMAIN/...` URL is behind Cloudflare Access (email OTP). Only `ssh` and `infisical` have CF Access service-token policies wired up in `tofu/stack/main.tf` (private stacks like Meilisearch use the email-OTP policy only), so plain script-style curl from external CI **won't work** without first adding a service-token policy for this stack. Two workable options:
     - **Browser:** log in once via OTP, then use the dashboard / browser-based clients while the cookie is valid.
     - **Headless CLI:** [`cloudflared access curl`](https://developers.cloudflare.com/cloudflare-one/identity/users/short-lived-certificates/) — interactively opens the OTP login in your browser the first time, caches a short-lived cert, then wraps subsequent curls.

   Example from a code-server terminal (inside the network, no CF Access in the path). Secret-handling note: even with shell-variable expansion the master key shows up in `ps` while curl runs. For a quick interactive command that's acceptable; for any persistent script, derive a scoped (read-only / per-index) API key via `POST /keys` and use that instead — the docs section below covers it.
   ```bash
   # Create an index
   curl -X POST 'http://meilisearch:7700/indexes' \
     -H "Authorization: Bearer $MEILISEARCH_MASTER_KEY" \
     -H 'Content-Type: application/json' \
     -d '{"uid":"docs","primaryKey":"id"}'

   # Search
   curl 'http://meilisearch:7700/indexes/docs/search?q=hello' \
     -H "Authorization: Bearer $MEILISEARCH_MASTER_KEY"
   ```
4. Derive scoped per-index API keys for your apps via `POST /keys` (read-only for a search frontend, write-only for an indexer, etc.)
5. If you want the preview dashboard for local exploration, override `MEILI_ENV=development` via the `MEILI_ENV` env var in your deployment — the compose file uses `${MEILI_ENV:-production}` so an outer-shell override (or a `.env` entry) takes effect on the next compose-up. NOT recommended for shared/public deployments — `production` enforces stricter API behavior.

### Nexus-Stack use cases

- **RAG companion to Chroma:** Crawl4AI scrapes a docs site (which already returns clean Markdown / JSON) → POST documents to Meilisearch → Big-AGI / Dify queries Meilisearch for keyword hits alongside Chroma's semantic hits (hybrid search). Each engine compensates for the other's weakness (Chroma misses exact-token matches, Meilisearch misses semantic paraphrases).
- **Class-wide doc search:** students extract text from course PDFs / notes / transcripts first (e.g. `pypdf` / `pdfminer.six` / `markitdown` from the code-server terminal), then POST the resulting JSON documents to the REST API. Meilisearch indexes structured JSON — it does NOT accept raw PDFs / Office files / binaries directly.
- **Quick "grep but ranked":** point Meilisearch at any JSON / Markdown / log dataset students are working with in code-server. Faster + nicer ranking than `grep`/`ripgrep` for prose.

### Auth model

Two layers, defense in depth:

| Layer | Where | Gates |
|---|---|---|
| **Cloudflare Access (email OTP)** | edge — before any traffic reaches the container | All HTTP requests to `https://meilisearch.<domain>` |
| **`MEILI_MASTER_KEY`** | in-container — Meilisearch checks per request | All `/indexes`, `/documents`, `/search`, `/keys` endpoints |

The master key is generated by OpenTofu (`random_password.meilisearch_master_key`, 32 chars) and pushed to Infisical at deploy time — never written into the repo. From the master key you derive scoped keys via the [`/keys` API](https://www.meilisearch.com/docs/reference/api/keys) (e.g. a read-only key for a search frontend, a write-only key for an indexer).

### Data persistence

Index data lives at `/mnt/nexus-data/meilisearch/` on the host, bind-mounted into `/meili_data` inside the container. **`/mnt/nexus-data/` itself is ephemeral host storage** (RFC 0001 cutover replaced the Hetzner block volume with R2 snapshot/restore). To make indexes survive teardown + spin-up, a follow-up PR needs to do BOTH:

1. Add the path as an `RsyncTarget` in `src/nexus_deploy/s3_restore.py::standard_targets` so it's included in the snapshot/restore cycle.
2. Add the compose file to `_STANDARD_STOP_COMPOSE_FILES` in the same module so the container is stopped BEFORE the rsync. Meilisearch's index format is LMDB-style (memory-mapped); snapshotting a running LMDB is unsafe (page-table corruption / partial-write visibility) — same atomicity rule that gitea/dify/metabase already follow. Skipping the stop step would produce snapshots that occasionally fail to restore.

Not done in this PR because typical usage is "rebuild the index from source on every spin-up" (e.g. Crawl4AI scrapes → POSTs documents fresh on each deploy).

### Telemetry

`MEILI_NO_ANALYTICS=true` disables Meilisearch's anonymous usage telemetry. Same convention as other Nexus-Stack services with upstream-telemetry opt-outs (Dozzle, Metabase). Reference: [Meilisearch telemetry docs](https://www.meilisearch.com/docs/learn/resources/telemetry).
