---
title: "Crawl4AI"
---

## Crawl4AI

![Crawl4AI](https://img.shields.io/badge/Crawl4AI-1B6CA8?logo=googlechrome&logoColor=white)

**LLM-friendly web crawler that returns clean Markdown for RAG ingestion**

Crawl4AI scrapes web pages and emits clean Markdown, JSON, or structured extracts ready for LLM prompts and RAG pipelines. Exposes both a REST API (`/crawl`, `/extract`) and an interactive Playground UI for ad-hoc experiments. Features include:

- Headless Chromium rendering (handles JS-heavy SPAs)
- Markdown / JSON / structured-extract output formats
- CSS-selector and LLM-driven extraction strategies
- Concurrent multi-URL crawling
- No database — stateless, in-memory cache only

| Setting | Value |
|---------|-------|
| Default Port | `11235` |
| Suggested Subdomain | `crawl4ai` |
| Public Access | No (protected by Cloudflare Access) |
| Persistence | None (stateless, in-memory cache only) |
| Website | [github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) |
| Source | [GitHub](https://github.com/unclecode/crawl4ai) |

### Usage

1. Open `https://crawl4ai.<domain>` and authenticate via Cloudflare Access.
2. Go to `/playground` for the interactive UI, or POST against the REST API at `/crawl` (e.g. `{ "url": "https://example.com" }`).
3. Pipe the resulting Markdown into Big-AGI, Dify, Kestra, or any other LLM workflow as RAG context.

### Security note

The container ships with `CRAWL4AI_HOOKS_ENABLED=false`. Upstream Crawl4AI's "hooks" feature lets API callers execute arbitrary Python from request bodies — useful for custom extraction logic, but a remote-code-execution risk for any caller who reaches the API.

Cloudflare Access ensures only authenticated users reach the API, but it does **not** constrain what those authenticated users can do once inside. For a multi-student class environment, hooks are therefore disabled by default. If you operate a single-user setup and explicitly want the hooks feature, flip the env var in [stacks/crawl4ai/docker-compose.yml](../../stacks/crawl4ai/docker-compose.yml) and re-spin-up.

### Operational note: shared memory

The container is started with `shm_size: 1g`. Crawl4AI bundles a Playwright browser pool for JS-heavy pages, which needs more than Docker's default 64 MB shared memory or it crashes on the first complex page render. The current 2 GB memory limit gives ~600 MB idle headroom and copes with parallel render bursts up to about a dozen concurrent crawls.
