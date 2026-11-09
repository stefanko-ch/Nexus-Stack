---
title: "AnythingLLM"
---

## AnythingLLM

![AnythingLLM](https://img.shields.io/badge/AnythingLLM-0E0F0F?logoColor=white)

**Chat with your documents, on local or hosted models**

AnythingLLM turns uploaded documents into chat workspaces. Files are split, embedded and stored in a built-in vector database, and the answers cite their sources. Agents, web browsing and a developer API come with it.

| Setting | Value |
|---------|-------|
| Default Port | `8121` (bound to `127.0.0.1` on the host; container port `3001`) |
| Suggested Subdomain | `anythingllm` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Instance password, generated per deployment (Infisical folder `anythingllm`) |
| Persistence | Docker volume `anythingllm-storage` |
| Website | [anythingllm.com](https://anythingllm.com) |
| Source | [GitHub](https://github.com/Mintplex-Labs/anything-llm) |

### AnythingLLM next to Open Notebook and Dify

[Dify](dify.md) builds LLM apps and workflows; [Open Notebook](open-notebook.md) is a research notebook. AnythingLLM is the shortest way from a folder of PDFs to a chat over them.

### First steps

1. Pull a model in the [Ollama](ollama.md) stack. AnythingLLM is preset for `ollama:11434` with `llama3.2`:

   ```bash
   docker exec ollama ollama pull llama3.2
   ```

2. Open `https://anythingllm.<domain>` and enter `ANYTHINGLLM_PASSWORD` from Infisical.
3. Create a workspace, upload documents and ask questions about them. Embeddings run inside AnythingLLM with its built-in model, so no embedding provider is needed.

Any other model or provider can be chosen in the settings, for example [LiteLLM](litellm.md) or a hosted API.

To get clean text out of complex PDFs first, run them through [Docling Serve](docling.md).

### Authentication

The instance runs in password-protected single-user mode: one password, `AUTH_TOKEN`, for everyone who passes Cloudflare Access. Without it the API and the settings, provider API keys included, would be open. Telemetry is off.

AnythingLLM can be switched to multi-user mode in its settings, with its own admin and users. That switch cannot be undone.

### Persistence

Documents, vectors, chats and settings are in `anythingllm-storage`.

- **`rebuild` (default): they do not survive a teardown.** AnythingLLM is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
