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

API keys for upstream LLM providers are stored **in the browser**, not on the server. Big-AGI never sees or persists them — each request from the browser to OpenAI / Anthropic / etc. is direct (proxied only by Cloudflare Tunnel for transport). This means the keys are gone if the browser's storage is cleared, but it also means there's no server-side secret to manage or leak.
