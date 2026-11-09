---
title: "Arize Phoenix"
---

## Arize Phoenix

![Arize Phoenix](https://img.shields.io/badge/Arize_Phoenix-F56565?logoColor=white)

**Tracing and evaluation for LLM applications**

Phoenix collects OpenTelemetry traces from LLM applications and shows each call with its prompt, response, token counts and latency. It also runs evaluations and experiments over datasets of examples. The [OpenInference](https://github.com/Arize-ai/openinference) instrumentations cover LangChain, LlamaIndex, the OpenAI SDK, LiteLLM and others. Next to [Langfuse](langfuse.md) it leans towards evaluation.

| Setting | Value |
|---------|-------|
| URL | `https://phoenix.<domain>` |
| In-cluster | `http://phoenix:6006/v1/traces` (OTLP over HTTP), `phoenix:4317` (OTLP gRPC) |
| Login | `admin@localhost` |
| Credentials | Initial password generated per deployment (Infisical folder `phoenix`); Phoenix asks for a new one at the first login |
| Persistence | Docker volume `phoenix-data` (SQLite) |
| Licence | Elastic License 2.0 — not an OSI licence |
| Website | [phoenix.arize.com](https://phoenix.arize.com) |

### First steps

1. Open `https://phoenix.<domain>` and log in as `admin@localhost` with `PHOENIX_PASSWORD` from Infisical. Phoenix then asks for a new password. Infisical keeps the initial one, so note the new one yourself.
2. Under **Settings → API Keys**, create a system key for sending traces.
3. In a notebook, instrument an application and point it at Phoenix:

```python
import os
from phoenix.otel import register  # pip install arize-phoenix-otel openinference-instrumentation-openai

os.environ["PHOENIX_API_KEY"] = "<API key>"
tracer_provider = register(project_name="demo", endpoint="http://phoenix:6006/v1/traces", auto_instrument=True)
```

Calls made through an instrumented library, for example to the [Ollama](ollama.md) stack through the OpenAI SDK, then appear in the project.

Tested:
- the admin login, with Phoenix flagging the password for reset;
- the API and the OTLP endpoint refused anonymous requests (`401`);
- a wrong password refused (`401`);
- the login kept across a restart.

**Not tried here:** sending traces from an instrumented application.

### Settings

- **Authentication** is on (`PHOENIX_ENABLE_AUTH`), with a generated signing secret. By default Phoenix runs with no login at all.
- **Secure cookies** and **the CSRF origin check** are set for the public URL. Without `PHOENIX_CSRF_TRUSTED_ORIGINS`, Phoenix does not check the origin at all.
- **The web analytics** (FullStory, Scarf) are off.

### Licence

Phoenix is under the Elastic License 2.0:
- self-hosting and modifying it are permitted;
- offering it as a managed service is not;
- it is not an OSI licence;
- Arize states it has no feature gates.

### Resources

It used about 420 MB. The container limit is 2 GB, the same as Phoenix's Helm chart.

### Persistence

Traces, datasets, experiments and users are in SQLite in `phoenix-data`.

- **`rebuild` (default): they do not survive a teardown.** Phoenix is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
