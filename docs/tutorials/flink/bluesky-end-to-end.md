---
title: "Bluesky end-to-end: Redpanda Connect → Flink SQL"
description: "End-to-end walkthrough that chains the Bluesky-to-Redpanda ingest and the Flink-SQL-on-Redpanda query into one guided run"
order: 3
---

# Bluesky Real-Time Streaming with Flink SQL

This tutorial walks through streaming live Bluesky posts into Redpanda and querying them with Flink SQL via Dinky.

## Prerequisites

Enable the following services in the Control Plane:
- **Redpanda** (Kafka-compatible broker)
- **Redpanda Connect** (data streaming framework)
- **Redpanda Console** (web UI for viewing topics)
- **Flink** (stream processing engine)
- **Dinky** (Flink SQL IDE)
- **code-server** (VS Code in the browser)

## Step 1: Start the Bluesky Stream (Code Server)

Open **code-server** (`https://code.YOUR_DOMAIN`) and open a terminal.

Create the stream config file:

```bash
cat > /tmp/bluesky.yaml << 'EOF'
input:
  websocket:
    url: "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
pipeline:
  processors:
    - mapping: |
        root.did = this.did
        root.time_us = this.time_us
        root.operation = this.commit.operation
        root.text = this.commit.record.text
        root.created_at = this.commit.record.createdAt
        root.langs = this.commit.record.langs
        root.reply_parent = this.commit.record.reply.parent.uri | null
        root.reply_root = this.commit.record.reply.root.uri | null
        root.is_reply = this.commit.record.reply != null
        root.embed = this.commit.record.embed | null
        root.facets = this.commit.record.facets | null
        root.timestamp = now()
output:
  kafka:
    addresses: ["redpanda:9092"]
    topic: bluesky-posts
EOF
```

Push it to Redpanda Connect via the REST API:

```bash
curl -s -X POST http://redpanda-connect:4195/streams/bluesky \
  -H "Content-Type: application/yaml" \
  --data-binary @/tmp/bluesky.yaml
```

Verify the stream is running:

```bash
curl -s http://redpanda-connect:4195/streams | jq
```

You should see `"bluesky": {"active": true, ...}`.

### Stopping the Stream

```bash
curl -s -X DELETE http://redpanda-connect:4195/streams/bluesky
```

## Step 2: Verify Data in Redpanda Console

Open **Redpanda Console** (`https://redpanda-console.YOUR_DOMAIN`).

Navigate to **Topics** → **bluesky-posts**. You should see messages arriving in real-time (~50-100 per second).

## Step 3: Set Up Dinky (First Time Only)

### 3.1 Login

Open **Dinky** (`https://dinky.YOUR_DOMAIN`).

- **Username:** `admin`
- **Password:** Available in Infisical under `dinky/DINKY_PASSWORD`

### 3.2 Register Flink Cluster

1. Go to **Registration Center** → **Cluster** → **Flink Instance**
2. Click **Add**
3. Set:
   - **Name:** `nexus-sink` (or any name)
   - **JM Address:** `http://flink-jobmanager:8081`
4. **Save** and verify the status shows **Normal** (green)

## Step 4: Create the Source Table (Dinky)

In **Data Studio**, create a new task (type: **FlinkSQL**).

Configure the task:
- **Catalog:** DefaultCatalog
- **Cluster:** nexus-sink (standalone)

Execute the following SQL:

```sql
CREATE TABLE IF NOT EXISTS bluesky_posts (
    did STRING,
    time_us BIGINT,
    operation STRING,
    `text` STRING,
    created_at STRING,
    langs ARRAY<STRING>,
    reply_parent STRING,
    reply_root STRING,
    is_reply BOOLEAN,
    embed STRING,
    facets STRING,
    `timestamp` STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'bluesky-posts',
    'properties.bootstrap.servers' = 'redpanda:9092',
    'properties.group.id' = 'flink-bluesky',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);
```

> This only needs to be done **once** — the DefaultCatalog persists table definitions across tasks.

## Step 5: Query Bluesky Posts

Create a new task and run:

```sql
SELECT `text`, langs, created_at, is_reply FROM bluesky_posts;
```

Results appear in the **Result** tab as posts arrive in real-time. Stop the job with the red stop button.

## Step 6: Stream Filtering — Write Back to Redpanda

### English Posts Only

```sql
CREATE TABLE IF NOT EXISTS bluesky_english (
    did STRING,
    `text` STRING,
    created_at STRING,
    is_reply BOOLEAN,
    `timestamp` STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'bluesky-english',
    'properties.bootstrap.servers' = 'redpanda:9092',
    'format' = 'json'
);

INSERT INTO bluesky_english
SELECT did, `text`, created_at, is_reply, `timestamp`
FROM bluesky_posts
WHERE langs[1] = 'en';
```

### German Posts Only

```sql
CREATE TABLE IF NOT EXISTS bluesky_german (
    did STRING,
    `text` STRING,
    created_at STRING,
    is_reply BOOLEAN,
    `timestamp` STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'bluesky-german',
    'properties.bootstrap.servers' = 'redpanda:9092',
    'format' = 'json'
);

INSERT INTO bluesky_german
SELECT did, `text`, created_at, is_reply, `timestamp`
FROM bluesky_posts
WHERE langs[1] = 'de';
```

These `INSERT INTO` statements start **continuous streaming jobs** that filter and forward posts in real-time. Check the new topics in Redpanda Console.

## Architecture Overview

```
Bluesky Jetstream (WebSocket)
        │
        ▼
┌─────────────────┐      ┌─────────────────┐
│ Redpanda Connect │─────▶│    Redpanda      │
│ (bluesky stream) │      │  bluesky-posts   │
└─────────────────┘      └────────┬─────────┘
                                  │
                          ┌───────┴────────┐
                          ▼                ▼
                   ┌────────────┐   ┌────────────┐
                   │ Flink SQL  │   │ Flink SQL  │
                   │ (filter)   │   │ (filter)   │
                   └──────┬─────┘   └──────┬─────┘
                          ▼                ▼
                   ┌────────────┐   ┌────────────┐
                   │  Redpanda  │   │  Redpanda  │
                   │  english   │   │  german    │
                   └────────────┘   └────────────┘
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Object 'bluesky_posts' not found` | Run the CREATE TABLE first, or set catalog to **DefaultCatalog** |
| `Table already exists` | Use `CREATE TABLE IF NOT EXISTS` or `DROP TABLE` first |
| `Property group.id is required` | Add `'properties.group.id'` to the WITH clause |
| No data in Result tab | Check that the Bluesky stream is running in Redpanda Connect |
| Flink cluster not reachable | Go to Registration Center → verify cluster status is **Normal** |
