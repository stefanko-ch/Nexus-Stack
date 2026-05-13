---
title: "Big-AGI"
---

## Big-AGI

![Big-AGI](https://img.shields.io/badge/Big--AGI-FF6B35?logo=openai&logoColor=white)

**Stateless multi-LLM web UI for OpenAI, Anthropic, and local LLM endpoints**

Big-AGI is a browser-based UI for interacting with multiple large language model providers without a server-side database. Conversation history and API keys live in the browser's LocalStorage. Features include:
- Support for OpenAI, Anthropic, local Ollama, and custom OpenAI-compatible endpoints
- Model switching mid-conversation and side-by-side multi-model comparison
- Prompt templates and persona management
- Conversation export / import (JSON, Markdown)
- Markdown rendering with code-block syntax highlighting

| Setting | Value |
|---------|-------|
| Default Port | `3006` |
| Suggested Subdomain | `big-agi` |
| Public Access | No (protected by Cloudflare Access) |
| Persistence | Browser LocalStorage (no server-side state) |
| Website | [github.com/enricoros/big-agi](https://github.com/enricoros/big-agi) |
| Source | [GitHub](https://github.com/enricoros/big-agi) |

### Usage

1. Open `https://big-agi.<domain>` and authenticate via Cloudflare Access.
2. Open **Models** → **Add Model** → paste an API key for OpenAI, Anthropic, or point at a local Ollama endpoint.
3. Start a new chat. Conversation history persists in the browser's LocalStorage; it does **not** sync across devices or survive a browser-data wipe.

### Note on API keys

API keys for upstream LLM providers are entered in the browser UI and **persisted in the browser's LocalStorage only** — the Big-AGI container has no database, no env-var injection, and no on-disk store for these keys. So if you clear browser data, the keys are gone; there's no server-side secret to rotate or leak.

**But — and this is the important nuance** — Big-AGI is a Next.js app, and browsers can't call OpenAI / Anthropic / etc. directly because of CORS. So when you send a message, the actual request flow is:

1. Your browser POSTs the prompt **and** the API key to a server-side route on the Big-AGI container (e.g. `/api/llms/...`).
2. The container's Next.js handler reads the key from the request body and uses it to call the upstream provider.
3. The provider's response streams back through the container to your browser.

Net consequence: the key **is** in the container's request path on every message. The container doesn't log it or persist it (it's in memory for the lifetime of one request), but anyone with shell access to the container during a request — or who could MITM container ↔ upstream-provider traffic — could observe it. Cloudflare Tunnel only protects the **browser ↔ container** segment, not the container ↔ OpenAI segment.

For a classroom or self-hosted setup, this is usually acceptable — you're the only operator with shell access. If your threat model includes the operator being adversarial (e.g. multi-tenant Big-AGI for untrusted users), this stack is not the right choice.
