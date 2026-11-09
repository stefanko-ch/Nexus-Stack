---
title: "SearXNG"
---

## SearXNG

![SearXNG](https://img.shields.io/badge/SearXNG-3050FF?logo=searxng&logoColor=white)

**Private metasearch engine**

SearXNG sends a query to many search engines at once and merges the results. There are no ads, no profiling and no tracking cookies.

| Setting | Value |
|---------|-------|
| Default Port | `8130` (bound to `127.0.0.1` on the host; container port 8080) |
| Suggested Subdomain | `searxng` |
| Public Access | No (protected by Cloudflare Access) |
| In-cluster | `http://searxng:8080` (JSON: `/search?q=...&format=json`) |
| Credentials | None — Cloudflare Access is the only gate |
| Persistence | Docker volume `searxng-cache` (cache only) |
| Website | [docs.searxng.org](https://docs.searxng.org) |

### Where it fits

SearXNG is the web search behind [Perplexica](perplexica.md) and [GPT Researcher](gpt-researcher.md). Both call its JSON API, and need this stack enabled.

Notebooks and flows can use the same API for their own searches:

```python
import requests

r = requests.get("http://searxng:8080/search", params={"q": "apache iceberg", "format": "json"})
for hit in r.json()["results"][:5]:
    print(hit["title"], hit["url"])
```

That request was tested against the stack.

### Configuration

`stacks/searxng/settings.yml` keeps SearXNG's defaults and changes three things:

- The JSON format is on.
- The bot limiter is off. It would need a Valkey instance, and behind Access it only gets in the way.
- The image proxy is on.

The secret key is generated per deployment (`SEARXNG_SECRET`).

### Notes

- Some engines answer server traffic with CAPTCHAs (DuckDuckGo did in a local test). SearXNG skips them and uses the rest.
- The Tor-only engines in the defaults fail to load, which the log reports. This is harmless.
