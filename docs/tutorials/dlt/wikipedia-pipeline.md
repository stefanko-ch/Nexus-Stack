---
title: "Your first dlt pipeline: Wikipedia pageviews"
description: "Build a pipeline that fetches monthly Wikipedia pageview counts from a public API and loads them into Postgres"
order: 2
---

# Your first dlt pipeline: Wikipedia pageviews

This tutorial builds a complete dlt pipeline from scratch. You'll fetch monthly pageview counts for a handful of Wikipedia articles from the free Wikimedia API and load them into your Nexus Postgres database. By the end you'll understand the three building blocks every dlt pipeline is made of.

## Prerequisites

- [Setup complete](./setup.md) — virtual environment active, dlt installed, Postgres credentials in `.dlt/secrets.toml`
- `code-server` terminal open, working directory `~/nexus-<your-domain>-workspace/dlt`

## psql availability

`psql` is **pre-installed** in the code-server image (via the `postgresql-client` apt package — see [the code-server stack docs](/docs/stacks/code-server/#pre-installed-data-tooling)), so you can use it directly without any setup step. Skip if you're on an older image — run `psql --version` first to confirm; if it fails, install with `sudo apt-get update && sudo apt-get install -y postgresql-client` (session-only fallback).

## The script

Create `wikipedia_pipeline.py` in your `dlt/` directory:

```python
import dlt
from dlt.sources.helpers import requests
from datetime import datetime
from typing import Iterator

ARTICLES = [
    "Data_engineering",
    "Data_science",
    "Large_language_model",
]

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
HEADERS = {"User-Agent": "dlt-nexus-pipeline/1.0"}


@dlt.resource(
    name="pageviews",
    primary_key=["article", "timestamp"],
    write_disposition="replace",
)
def wikipedia_pageviews(
    start: str = "20240101",
    end: str = None,
    granularity: str = "monthly",
) -> Iterator[dict]:
    if end is None:
        end = datetime.now().strftime("%Y%m%d")
    for article in ARTICLES:
        url = f"{BASE_URL}/en.wikipedia/all-access/all-agents/{article}/{granularity}/{start}/{end}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        for item in response.json().get("items", []):
            yield item


if __name__ == "__main__":
    pipeline = dlt.pipeline(
        pipeline_name="wikipedia_pipeline",
        destination="postgres",
        dataset_name="wikipedia",
    )
    info = pipeline.run(wikipedia_pageviews())
    print(info)
```

## Run it

```bash
python wikipedia_pipeline.py
```

Expected output:

```
Pipeline wikipedia_pipeline load step completed in 0.15 seconds
1 load package(s) were loaded to destination postgres and into dataset wikipedia
The postgres destination used postgresql://nexus-postgres:***@postgres:5432/postgres location to store data
Load package 1778429304.0475023 is LOADED and contains no failed jobs
```

## Verify the data

Check which tables dlt created:

```bash
psql -h postgres -U nexus-postgres -d postgres -c "\dt wikipedia.*"
```

psql will prompt for the password. If you prefer to skip the prompt in your session, run `export PGPASSWORD="your_password"` once in the terminal first — but never inline it in a committed script.

```
   Schema   |        Name         | Type  |     Owner
-----------+---------------------+-------+----------------
 wikipedia | _dlt_loads          | table | nexus-postgres
 wikipedia | _dlt_pipeline_state | table | nexus-postgres
 wikipedia | _dlt_version        | table | nexus-postgres
 wikipedia | pageviews           | table | nexus-postgres
```

Query the first few rows:

```bash
psql -h postgres -U nexus-postgres -d postgres \
  -c "SELECT article, timestamp, views FROM wikipedia.pageviews ORDER BY article, timestamp LIMIT 10;"
```

```
     article      | timestamp  | views
------------------+------------+-------
 Data_engineering | 2024010100 |  7454
 Data_engineering | 2024020100 |  6273
 Data_engineering | 2024030100 |  6732
 ...
```

The `timestamp` format is `YYYYMMDD00` — a Wikimedia convention where the trailing `00` is always a placeholder for the hour field in monthly aggregates.

## What just happened

Three pieces make every dlt pipeline:

**1. The resource** — `@dlt.resource` turns a Python generator into an extractable data source. The function `yield`s one dict per row. dlt infers the table schema automatically from the first yielded record: column names come from dict keys, types from the values.

**2. The pipeline** — `dlt.pipeline(...)` wires a source to a destination. `dataset_name="wikipedia"` becomes a Postgres schema. The `pipeline_name` is used to store pipeline state between runs (relevant in the next tutorial).

**3. `pipeline.run()`** — pulls every record from the generator, creates `wikipedia.pageviews` if it doesn't exist, and loads all rows. Takes a few seconds for a few hundred rows.

The three `_dlt_*` tables are dlt's own bookkeeping: `_dlt_loads` logs every run, `_dlt_version` records the dlt version that wrote the schema, and `_dlt_pipeline_state` stores the incremental cursor (covered in the next tutorial).

## Customise the articles

Edit the `ARTICLES` list at the top of the script to track any Wikipedia article. The article name must match the URL slug exactly — copy it from the Wikipedia address bar:

```
https://en.wikipedia.org/wiki/Apache_Kafka  →  "Apache_Kafka"
```

`write_disposition="replace"` drops and recreates `pageviews` on every run, so adding or removing articles takes effect immediately on the next run.

## What's next

`replace` is fine for exploration but wasteful: every run re-fetches all history just to overwrite the same rows. The next tutorial adds a **state cursor** so each run only fetches months that aren't in the database yet — [Wikipedia pipeline with incremental loading](./wikipedia-incremental.md).
