---
title: "Redpanda"
---

## Redpanda

![Redpanda](https://img.shields.io/badge/Redpanda-E4405F?logo=redpanda&logoColor=white)

**Kafka-compatible streaming platform**

Redpanda is a Kafka-compatible streaming data platform that is simpler, faster, and more cost-effective than Apache Kafka. Features include:
- 10x faster than Kafka with lower latency
- No JVM, no ZooKeeper dependencies
- 100% Kafka API compatible
- Built-in Schema Registry and HTTP Proxy
- Single binary deployment
- WebAssembly data transforms

| Setting | Value |
|---------|-------|
| Admin Panel Port | `9644` — internal only, reached via Cloudflare-Tunnel-fronted `https://redpanda.<domain>` |
| Kafka Port | `9092` — exposable via Hetzner firewall_rules |
| Schema Registry Port | `18081` — exposable via Hetzner firewall_rules |
| Suggested Subdomain | `redpanda` |
| Public Access | No (streaming infrastructure) |
| Website | [redpanda.com](https://redpanda.com) |
| Source | [GitHub](https://github.com/redpanda-data/redpanda) |

> ⚠️ The **Admin API on port 9644 cannot be opened via Hetzner firewall_rules** — only Kafka (9092) and Schema Registry (18081) appear in the Control Plane's firewall UI. The Admin API has no authentication of its own (anyone reaching it can create/delete SASL users, change cluster config, delete topics), so the only public access path is the Cloudflare-Tunnel-fronted admin panel, which is gated by Cloudflare Access at the edge.
