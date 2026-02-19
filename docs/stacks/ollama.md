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

Hetzner ARM servers (cax31 = Ampere Altra) do not have GPUs. All models run on CPU.
Recommended models for acceptable performance:

| Model | Parameters | Use Case |
|-------|-----------|----------|
| `llama3.2:1b` | 1B | Fast responses, simple tasks |
| `llama3.2:3b` | 3B | Good balance of speed and quality |
| `phi4-mini` | 3.8B | Reasoning and code |
| `gemma3:4b` | 4B | General purpose |
| `qwen2.5:7b` | 7B | Higher quality, slower |

### Getting Started

1. Enable "ollama" in the Control Plane and run Spin Up
2. Navigate to `https://ollama.YOUR_DOMAIN`
3. Register your admin account (first user = admin)
4. Pull a model via the UI or SSH:
   ```bash
   ssh nexus "docker exec ollama ollama pull llama3.2:1b"
   ```
5. Start chatting
