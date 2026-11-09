---
title: "Perplexica"
---

## Perplexica

![Perplexica](https://img.shields.io/badge/Perplexica-1F2937?logoColor=white)

**AI answer engine on local models and private search**

Perplexica answers a question the way Perplexity does. It searches the web through [SearXNG](searxng.md), reads the results, and writes an answer with numbered sources, using a model in [Ollama](ollama.md).

| Setting | Value |
|---------|-------|
| Default Port | `8129` (bound to `127.0.0.1` on the host; container port 3000) |
| Suggested Subdomain | `perplexica` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — Cloudflare Access is the only gate |
| Needs | the `searxng` and `ollama` stacks |
| Persistence | Docker volume `perplexica-data` (settings, chats) |
| Website | [GitHub](https://github.com/ItzCrazyKns/Perplexica) |

### First steps

1. Enable **searxng** and **ollama**. In Open WebUI, pull a chat model (for example `llama3.2`) and an embedding model (`nomic-embed-text`).
2. Open Perplexica. The setup screen already lists Ollama at `http://ollama:11434`, and SearXNG is preset. Pick the two models.
3. Ask a question.

Hosted providers such as OpenAI or Anthropic can be added in the same settings, with your own key.

### What was tested

Tested locally:

- Ollama and SearXNG URLs are preset from the environment.
- Ollama's models appear in `/api/providers`.
- Perplexica reaches SearXNG.
- A search request reached Ollama.

A complete answer was **not** obtained. With a 0.5B model on a laptop's CPU, the model calls took minutes each, and the request timed out first.

On the server, a model of the `llama3.2` class is the realistic minimum. Expect answers in tens of seconds, not instantly.

### Authentication

Perplexica has no accounts. The subdomain is behind Cloudflare Access. Perplexica is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.

### Persistence

Settings and chat history are in `perplexica-data`. The SearXNG and Ollama URLs are written to its config file on the first start.

- **`rebuild` (default): they do not survive a teardown.**
- **`snapshot`: they survive**, because the whole disk is imaged.
