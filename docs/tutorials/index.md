---
title: "Tutorials"
description: "Bite-sized how-tos for the most common Nexus-Stack workflows — each 5-15 min, no framework assumed"
order: 0
---

# Tutorials

Bite-sized how-tos for the most common Nexus-Stack workflows. Each tutorial is self-contained, takes 5–15 minutes, and assumes you've already deployed a Nexus-Stack server and enabled the services it talks about.

The goal: give you one focused skill per page, so you can stitch the ones you need into your own pipeline without reading a monolithic end-to-end guide.

## Start here if…

| You want to… | Start with |
|---|---|
| Send and receive events on Redpanda from Python | [Redpanda → Send your first event](./redpanda/first-producer) |
| Pipe an external stream into Redpanda without writing code | [Redpanda Connect → Stream Bluesky firehose](./redpanda-connect/bluesky-stream) |
| Write SQL against a live event stream | [Flink → Query a Redpanda topic with Flink SQL](./flink/flink-sql-on-redpanda) |
| Land streaming data in a Delta table on Databricks | [Spark → Write a Kafka stream to a Bronze Delta table](./spark/bronze-delta) |
| Read the Nexus data lake from a Databricks notebook | [Databricks → Read and write R2](./databricks/r2-datalake) |
| Just get a terminal and Python working inside Nexus-Stack | [Code-Server → Run curl in the terminal](./code-server/terminal-curl) |

## Categories

| Category | Covers | Count |
|---|---|---|
| **[Code-Server](./code-server/)** | Terminal, internal service hostnames, Python venv setup with uv | 2 |
| **[Redpanda](./redpanda/)** | Topics, Python producer/consumer, partitions, consumer groups, in-Python aggregation | 8 |
| **[Redpanda Connect](./redpanda-connect/)** | YAML-driven pipelines — deploy, manage, real-world Bluesky example | 2 |
| **[dlt](./dlt/)** | Ingest public APIs into Postgres — first pipeline, incremental loading, two resources, your own source | 5 |
| **[Flink](./flink/)** | Dinky setup, Flink SQL against Redpanda, end-to-end Bluesky walkthrough | 3 |
| **[Spark Structured Streaming](./spark/)** | Databricks streaming from rate source → Redpanda read → JSON parsing → Bronze Delta | 4 |
| **[Databricks](./databricks/)** | External Databricks ↔ Nexus workflows — R2 data lake from notebooks | 1 |

## How to use these

- **Each tutorial names its prerequisites** at the top. If you're landing on a specific one from a search engine, check that list first.
- **Sample data pattern.** Most Redpanda / Spark tutorials use a topic named `sensors` with JSON payloads `{"sensor": "...", "reading": 42.5, "timestamp": 1713...}`. You can produce your own with the Python producer tutorial or bring any other data in.
- **Internal hostnames.** Code examples use Docker service names (`redpanda:9092`, `flink-jobmanager:8081`, `redpanda-connect:4195`) because the tutorials run inside code-server on the same Docker network. These don't resolve from your laptop — see [Run curl in the code-server terminal](./code-server/terminal-curl) for why.
- **Nothing is course-specific.** The tutorials were designed to be reusable by anyone running Nexus-Stack, not tied to a specific class or curriculum.

## What's not here

- **Full end-to-end projects** — tutorials are skill-level, not project-level. The closest thing to an end-to-end walkthrough is the [Bluesky → Flink](./flink/bluesky-end-to-end) guide, which chains two separate tutorials into one run.
- **Setup and provisioning** — see the [Setup Guide](../admin-guides/setup-guide.md) for getting Nexus-Stack up in the first place.
- **Per-service reference docs** — see [Stacks](/docs/stacks/) for the catalog of every service, its port, and its quirks.

Screenshots will be added to the tutorials over time; the prose descriptions are written to be followable without them.
