---
title: "Whisper ASR Webservice"
---

## Whisper ASR Webservice

![Whisper ASR](https://img.shields.io/badge/Whisper_ASR-412991?logo=openai&logoColor=white)

**Speech-to-text API based on OpenAI Whisper**

Whisper ASR Webservice transcribes and translates audio on the server, with no external API. It uses faster-whisper with the `base` model, on the CPU.

| Setting | Value |
|---------|-------|
| Default Port | `8127` (bound to `127.0.0.1` on the host; container port 9000) |
| Suggested Subdomain | `whisper` |
| Public Access | No (protected by Cloudflare Access) |
| In-cluster | `http://whisper:9000` |
| Credentials | None — Cloudflare Access is the only gate |
| Persistence | Docker volume `whisper-models` (model cache) |
| Website | [ahmetoner.com/whisper-asr-webservice](https://ahmetoner.com/whisper-asr-webservice/) |

### Where it fits

Voice notes, interviews and meeting recordings become text that the RAG and LLM stacks can work with: [Open Notebook](open-notebook.md), [AnythingLLM](anythingllm.md), [Dify](dify.md).

### First steps

The Swagger UI at `https://whisper.<domain>/docs` tries the API in the browser. From a notebook:

```python
import requests

with open("meeting.wav", "rb") as f:
    r = requests.post("http://whisper:9000/asr",
                      params={"output": "txt", "language": "en"},
                      files={"audio_file": f})
print(r.text)
```

`output` can also be `json`, `srt`, `vtt` or `tsv`. `task=translate` translates into English. Without `language`, the model detects it.

A short English recording was transcribed correctly in under a second. Throughput on the server's CPU was not measured.

### Models

`base` is a compromise between speed and accuracy. `small` and `medium` are more accurate, and slower, and need more memory than the 2 GB limit in the compose file. The model is set by `ASR_MODEL` in `stacks/whisper/docker-compose.yml`.

The model is downloaded on first start and cached in `whisper-models`. It is unloaded after ten idle minutes and reloaded on the next request.

### Authentication

The API has none. The subdomain is behind Cloudflare Access, and containers on `app-network` call it directly. Whisper is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.
