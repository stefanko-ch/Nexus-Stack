## Ollama + Open WebUI

![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)

**Local LLM inference with Open WebUI chat interface**

Run large language models locally with Ollama as the inference backend and Open WebUI
as a ChatGPT-like chat interface. No data leaves your server.

| Setting | Value |
|---------|-------|
| Default Port | `8093` |
| Suggested Subdomain | `ollama` |
| Public Access | No (Cloudflare Access protected) |
| Default Enabled | No |
| Website | [openwebui.com](https://openwebui.com) |
| Source | [GitHub](https://github.com/open-webui/open-webui) |

### Architecture (2 containers)

| Container | Image | Purpose |
|-----------|-------|---------|
| `ollama` | `ollama/ollama:0.15.1` | LLM inference engine (internal only) |
| `open-webui` | `ghcr.io/open-webui/open-webui:v0.8.3` | Chat interface (exposed via subdomain) |

Ollama runs on an internal-only network (`ollama-internal`) and is not exposed externally.
Open WebUI connects to both `app-network` (for Cloudflare Tunnel access) and `ollama-internal`
(to reach the Ollama API).

### Data Storage

| Volume | Content |
|--------|---------|
| `ollama-data` | Downloaded LLM models |
| `open-webui-data` | Conversation history, user accounts, settings |

### Credentials

No pre-configured credentials. The **first user to register** becomes the admin.
After initial registration, additional users can be managed from the admin panel.

### CPU-Only Mode

> ⚠️ **No GPU available:** Hetzner ARM servers (cax31 = Ampere Altra) have no GPU.
> All models run on CPU only, which is significantly slower than GPU inference.

This means:
- Response generation takes longer (seconds to minutes depending on model size)
- Large models (13B+) are impractical — stick to 1B–7B parameter models
- First response after loading a model has an extra warm-up delay (~5–10s)

### Models

**No models are pre-installed.** After deployment, you must pull at least one model before you can start chatting.

#### Recommended models for CPU

| Model | Size on disk | Speed (CPU) | Best for |
|-------|-------------|-------------|----------|
| `llama3.2:1b` | ~1.3 GB | Very fast | Quick answers, simple tasks |
| `llama3.2:3b` | ~2.0 GB | Fast | General chat, good quality |
| `phi4-mini` | ~2.5 GB | Fast | Reasoning, coding |
| `gemma3:4b` | ~3.3 GB | Medium | General purpose |
| `qwen2.5:7b` | ~4.7 GB | Slow | Higher quality responses |
| `qwen2.5-coder:7b` | ~4.7 GB | Slow | Code generation |

> **Recommendation for getting started:** `llama3.2:3b` — good quality with acceptable speed on CPU.

#### How to pull a model

**Via SSH:**
```bash
ssh nexus "docker exec ollama ollama pull llama3.2:3b"
```

**Via Open WebUI:**
1. Admin Panel (top-left profile icon) → **Models**
2. Enter model name in the search field (e.g. `llama3.2:3b`) → Pull

All available models: [ollama.com/library](https://ollama.com/library)

#### Manage installed models

```bash
# List installed models
ssh nexus "docker exec ollama ollama list"

# Remove a model
ssh nexus "docker exec ollama ollama rm llama3.2:1b"
```

### Getting Started

1. Enable "ollama" in the Control Plane and run Spin Up
2. Navigate to `https://ollama.YOUR_DOMAIN`
3. Register your admin account (first user = admin)
4. Pull a model:
   ```bash
   ssh nexus "docker exec ollama ollama pull llama3.2:3b"
   ```
5. Start chatting
