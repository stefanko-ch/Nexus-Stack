---
title: "Microsoft Presidio"
---

## Microsoft Presidio

![Presidio](https://img.shields.io/badge/Presidio-0078D4?logoColor=white)

**PII detection and anonymization APIs**

Presidio finds personal data in text and rewrites it. It detects names, email addresses, phone numbers, IBANs, credit card numbers and more, using a spaCy NER model and pattern recognizers.

| Setting | Value |
|---------|-------|
| Analyzer | `http://presidio-analyzer:3000` (also `http://presidio:3000`) |
| Anonymizer | `http://presidio-anonymizer:3000` |
| Credentials | None — internal only |
| Web UI | None — internal only, no subdomain |
| Persistence | None (stateless) |
| Website | [microsoft.github.io/presidio](https://microsoft.github.io/presidio/) |

### Where it fits

Use it for data-governance and GDPR lessons: what counts as personal data, and the difference between masking, pseudonymising and encrypting.

It also fits in front of LLM pipelines, such as [Ollama](ollama.md), [Dify](dify.md) and [LiteLLM](litellm.md), to strip personal data from prompts and documents before they reach a model. **It reduces that risk; it does not remove it.** Detection is pattern- and model-based, and it misses entities: names in unusual forms, identifiers it has no recognizer for, personal data in other languages than the loaded models. Treat its output as masked, not as anonymous. Keep the other safeguards too: send only the data a task needs, prefer models that run on the server, and review what a pipeline sends.

### First steps

The analyzer returns where the entities are. The anonymizer takes the text and those results:

```python
import requests

text = "My name is John Smith, email john.smith@example.com, phone 212-555-0123"
found = requests.post("http://presidio-analyzer:3000/analyze",
                      json={"text": text, "language": "en"}).json()
result = requests.post("http://presidio-anonymizer:3000/anonymize",
                       json={"text": text, "analyzer_results": found}).json()
print(result["text"])
# My name is <PERSON>, email <EMAIL_ADDRESS>, phone <PHONE_NUMBER>
```

That request and output were tested against the stack. The anonymizer has more operators than `replace`: `mask`, `hash`, `redact` and a reversible `encrypt`. Each is set per entity type in `anonymizers`.

### Languages

The image's model is English (`en`). German or other languages need a custom image with the spaCy model and an NLP configuration. That is not part of this stack.

### Authentication

None. Both APIs are reachable only from containers on `app-network`. Presidio is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.
