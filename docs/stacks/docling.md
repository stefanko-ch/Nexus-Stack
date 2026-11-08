---
title: "Docling Serve"
---

## Docling Serve

![Docling](https://img.shields.io/badge/Docling-0F62FE?logoColor=white)

**Document conversion API: PDF, DOCX, PPTX and HTML to Markdown or JSON**

Docling turns documents into structured text for LLMs and search. Layout analysis recovers the reading order, headings and lists, table structure recognition rebuilds tables, and OCR handles scanned pages. Output is Markdown, JSON, HTML or plain text.

| Setting | Value |
|---------|-------|
| Default Port | `8118` (bound to `127.0.0.1` on the host; container port `5001`) |
| Web UI | `https://docling.<domain>/ui` |
| API docs | `https://docling.<domain>/docs` |
| In-cluster API | `http://docling:5001/v1/convert/source` |
| Suggested Subdomain | `docling` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | API key, generated per deployment (Infisical folder `docling`) |
| Persistence | None — conversions are not stored |
| Website | [docling-project.github.io](https://docling-project.github.io/docling/) |
| Source | [GitHub](https://github.com/docling-project/docling-serve) |

### Where it fits

Docling is the ingestion step in front of the RAG stacks: [Flowise](flowise.md), [Langflow](langflow.md), [Dify](dify.md) and [Open Notebook](open-notebook.md). It also feeds anything that indexes documents, such as [ParadeDB](paradedb.md), [Qdrant](qdrant.md) or [Weaviate](weaviate.md).

### Web UI

Open `https://docling.<domain>/ui`, click **Set API key** and paste `DOCLING_API_KEY` from Infisical. The UI keeps it for the browser session. Then drop a file or paste a URL and press **Convert**.

### API

Every call needs the key in an `X-Api-Key` header. Without it the API answers `401`.

```python
import requests

r = requests.post(
    "http://docling:5001/v1/convert/source",
    headers={"X-Api-Key": "<DOCLING_API_KEY>"},
    json={
        "sources": [{"kind": "http", "url": "https://arxiv.org/pdf/2206.01062"}],
        "options": {"to_formats": ["md"]},
    },
    timeout=300,
)
print(r.json()["document"]["md_content"][:500])
```

The call is synchronous and holds the connection until the conversion is done, so give it a long timeout. A 9-page paper took 16 seconds without OCR in testing. Files can be uploaded with `POST /v1/convert/file` instead.

### Resources

The CPU image carries the layout and table models, so nothing is downloaded at runtime and no GPU is needed. Memory was 1.6 GB after converting the paper above. The limit is 3 GB; large documents with OCR may need more.
