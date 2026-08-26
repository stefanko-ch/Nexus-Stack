---
title: "Databricks"
description: "Connect Databricks to Nexus-Stack services — R2 data lake, Delta tables, external integrations"
order: 0
---

# Databricks tutorials

These tutorials cover the external side of Nexus-Stack — the workflows that run inside a Databricks workspace and talk back to services running on your Nexus server.

Setup steps that belong on the Nexus side (saving the workspace host + token, syncing Infisical secrets to the `nexus` scope) live in the [Integrations user guide](/docs/guides/user-guides/integrations/). Everything here assumes that's already done.

## Tutorials

1. **[Read and write R2 from a Databricks notebook](./r2-datalake)** — connect to your Nexus R2 bucket from PySpark and boto3 using the synced `nexus` secret scope. First stop for any data-lake workflow.

## What's not in this category

- **Spark Structured Streaming from Redpanda → Delta** — lives in [Spark Structured Streaming](/docs/tutorials/spark/), because those tutorials are Spark-mechanics-first with Databricks as the execution environment. Come here for Databricks-specific connections; go there for Spark query patterns.
- **Git access to Nexus Forgejo from Databricks Repos** — see [stacks/git-proxy](/docs/stacks/git-proxy/) for the HTTPS proxy setup.
