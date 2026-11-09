---
title: "GPT Researcher"
---

## GPT Researcher

![GPT Researcher](https://img.shields.io/badge/GPT_Researcher-111827?logoColor=white)

**Autonomous research agent**

Give GPT Researcher a question. It plans sub-questions, searches the web, reads and filters the pages, and writes a report with citations.

| Setting | Value |
|---------|-------|
| Default Port | `8131` (bound to `127.0.0.1` on the host; container port 8000) |
| Suggested Subdomain | `gpt-researcher` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — Cloudflare Access is the only gate |
| Needs | the `searxng` and `ollama` stacks |
| Persistence | Docker volume `gpt-researcher-outputs` (reports) |
| Website | [gptr.dev](https://gptr.dev) |

### GPT Researcher next to Perplexica

[Perplexica](perplexica.md) answers a question in a paragraph. GPT Researcher writes a report: longer, structured, with a reference list, and exportable as Markdown, PDF or DOCX.

### Configuration

The stack is preset for private search and local models:

| Setting | Value |
|---|---|
| Retriever | `searx`, against `http://searxng:8080` |
| Language models | `ollama:llama3.2`, for the fast, smart and strategic roles |
| Embeddings | `ollama:nomic-embed-text` |

Enable **searxng** and **ollama** and pull both models in Ollama. To use other models, change the variables in `stacks/gpt-researcher/docker-compose.yml`. The format is `provider:model`.

GPT Researcher is tuned for large hosted models. A small local model writes shorter reports, and can fail on the long final report.

### Image

The published images stopped at 3.3.0 (2025) and are amd64 only. The stack builds v3.7.0 from its release archive on `python:3.12.13-slim`, for amd64 and arm64.

Upstream's image also installs Chromium and Firefox. This one does not: the default scraper (BeautifulSoup) needs no browser. The browser-based scrapers (`SCRAPER=browser`, `nodriver`) are therefore not available.

### What was tested

Tested locally:

- The image builds, and the web UI loads.
- The SearXNG retriever returns results from inside the container.
- Ollama is reachable.

A complete report was **not** obtained. With a 0.5B model on a laptop's CPU, a single model call took over a minute, and the run was stopped during planning.

On the server, a report with `llama3.2` will take minutes.

### Authentication

The web UI and its WebSocket API have no login. The subdomain is behind Cloudflare Access. GPT Researcher is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.
