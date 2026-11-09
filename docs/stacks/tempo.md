---
title: "Grafana Tempo"
---

## Grafana Tempo

![Tempo](https://img.shields.io/badge/Grafana_Tempo-F46800?logo=grafana&logoColor=white)

**Distributed tracing, with an OpenTelemetry Collector in front**

Tempo stores traces: the spans an application emits as a request passes through its services, with timings and attributes. The OpenTelemetry Collector next to it is the one endpoint applications send OTLP to.

| Setting | Value |
|---------|-------|
| OTLP endpoint | `tempo-otel-collector:4317` (gRPC), `http://tempo-otel-collector:4318` (HTTP) |
| Query API | `http://tempo:3200` (Grafana datasource) |
| Credentials | None — internal only |
| Web UI | None of its own — Grafana |
| Retention | 7 days |
| Persistence | Docker volume `tempo-data` |
| Website | [grafana.com/oss/tempo](https://grafana.com/oss/tempo/) |

### Where it fits

The [Grafana](grafana.md) stack has metrics (Prometheus) and logs (Loki). Tempo adds the third signal, traces.

### Seeing traces in Grafana

The Grafana stack does not provision a Tempo datasource, since Tempo is optional. Add it once: **Connections → Data sources → Add → Tempo**, URL `http://tempo:3200`, **Save & test**. Traces are then found under **Explore**.

### Sending a trace

Any OpenTelemetry SDK exports to the collector. With the Python SDK:

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

provider = TracerProvider(resource=Resource.create({"service.name": "nexus-demo"}))
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://tempo-otel-collector:4318/v1/traces")))
trace.set_tracer_provider(provider)

with trace.get_tracer("demo").start_as_current_span("hello"):
    pass
provider.shutdown()  # flushes the batch
```

The path collector → Tempo was tested with a raw OTLP/HTTP request; the SDK snippet above was not run here.

### Authentication

None. OTLP and Tempo's query API are reachable only from containers on `app-network`. Tempo is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.

### Notes

- Both images are distroless, without a shell, so neither container has a Docker healthcheck. Tempo's readiness is at `http://tempo:3200/ready`.
- The collector also accepts OTLP metrics and logs, so a client sending all three signals gets no errors. It only logs them; they are not stored.
- Tempo's anonymous usage reporting is switched off in `tempo.yaml`.

### Persistence

Traces are in `tempo-data` for seven days.

- **`rebuild` (default): they do not survive a teardown.**
- **`snapshot`: they survive**, because the whole disk is imaged.
