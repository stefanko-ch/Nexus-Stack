---
title: "Incremental loading with state"
description: "Add a cursor to your Wikipedia pipeline so each run only fetches months that aren't in Postgres yet"
order: 3
---

# Incremental loading with state

The previous tutorial used `write_disposition="replace"`, which drops and recreates the table on every run. That's fine for a handful of articles, but it re-fetches years of data each time. This tutorial rewrites the pipeline to fetch only what's new since the last run.

## Prerequisites

- [Setup complete](./setup.md)
- [Wikipedia pipeline tutorial](./wikipedia-pipeline.md) completed — you understand resources and `pipeline.run()`

## The script

Create `wikipedia_incremental.py`:

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

_metrics = {"api_calls": 0, "records_received": 0, "start": "", "end": ""}


@dlt.resource(
    name="pageviews",
    primary_key=["article", "timestamp"],
    write_disposition="merge",
)
def wikipedia_pageviews(
    end: str = None,
    full_refresh: bool = False,
    granularity: str = "monthly",
) -> Iterator[dict]:
    _metrics["api_calls"] = 0
    _metrics["records_received"] = 0

    if end is None:
        # Cap at the first of the current month — only fetch complete months
        end = datetime.now().replace(day=1).strftime("%Y%m%d")

    state = dlt.current.resource_state()
    last_timestamp = state.get("last_timestamp", "2024010100")

    start = "20240101" if full_refresh else last_timestamp[:8]
    _metrics["start"] = start
    _metrics["end"] = end

    # Cursor has caught up — nothing new to fetch this month
    if start >= end:
        return

    max_timestamp = last_timestamp

    for article in ARTICLES:
        url = f"{BASE_URL}/en.wikipedia/all-access/all-agents/{article}/{granularity}/{start}/{end}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        items = response.json().get("items", [])
        _metrics["api_calls"] += 1
        _metrics["records_received"] += len(items)
        for item in items:
            if item["timestamp"] > max_timestamp:
                max_timestamp = item["timestamp"]
            yield item

    state["last_timestamp"] = max_timestamp


if __name__ == "__main__":
    import sys
    full_refresh = "--full-refresh" in sys.argv

    pipeline = dlt.pipeline(
        pipeline_name="wikipedia_incremental",
        destination="postgres",
        dataset_name="wikipedia",
    )
    info = pipeline.run(wikipedia_pageviews(full_refresh=full_refresh))

    load_id = info.load_packages[0].load_id if info.load_packages else None
    records_written = 0
    if load_id:
        with pipeline.sql_client() as client:
            with client.execute_query(
                "SELECT count(*) FROM wikipedia.pageviews WHERE _dlt_load_id = %s", load_id
            ) as cursor:
                records_written = cursor.fetchone()[0]

    status = info.load_packages[0].state if info.load_packages else "N/A"
    print(f"\n{'='*42}")
    print(f"  Wikipedia Pageviews — Run Summary")
    print(f"{'='*42}")
    print(f"  Date range:       {_metrics['start']} → {_metrics['end']}")
    print(f"  API calls made:   {_metrics['api_calls']}")
    print(f"  Records received: {_metrics['records_received']}")
    print(f"  Records written:  {records_written}")
    print(f"  Load status:      {status}")
    print(f"{'='*42}\n")
```

## Run it

First run — loads all complete months since January 2024:

```bash
python wikipedia_incremental.py --full-refresh
```

```
==========================================
  Wikipedia Pageviews — Run Summary
==========================================
  Date range:       20240101 → 20260501
  API calls made:   3
  Records received: 87
  Records written:  87
  Load status:      loaded
==========================================
```

Second run — the cursor is already at the current month boundary, nothing to fetch:

```bash
python wikipedia_incremental.py
```

```
==========================================
  Wikipedia Pageviews — Run Summary
==========================================
  Date range:       20260501 → 20260501
  API calls made:   0
  Records received: 0
  Records written:  0
  Load status:      N/A
==========================================
```

Zero API calls, zero records — the pipeline detected that the cursor has caught up and returned early without touching the database. Next month's run will fetch only that month's data for each article.

## Optional: Verify the data

**Option A — CloudBeaver (recommended):** Open `https://cloudbeaver.<your-domain>` in your browser. Connect to the Nexus Postgres database if you haven't already (host `postgres`, port `5432`, database `postgres`, user `nexus-postgres`), then expand **postgres → wikipedia → Tables → pageviews** in the left panel. Right-click the table and choose **View data** to browse rows and filter by `article` or `timestamp`.

You can also run SQL directly — open a new SQL script and try:

```sql
SELECT article, timestamp, views
FROM wikipedia.pageviews
ORDER BY article, timestamp;
```

**Option B — psql in the terminal:** `psql` is pre-installed in the code-server image (see [the code-server stack docs](/docs/stacks/code-server/#pre-installed-data-tooling)). Run `psql --version` first to confirm; on older images that haven't been rebuilt yet, install it once per session with `sudo apt-get update && sudo apt-get install -y postgresql-client`.

Query:

```bash
psql -h postgres -U nexus-postgres -d postgres \
  -c "SELECT article, timestamp, views FROM wikipedia.pageviews ORDER BY article, timestamp LIMIT 10;"
```

Either way you should see 87 rows spread across three articles, each with a `YYYYMMDD00` timestamp and a monthly view count.

## What changed from the simple pipeline

**`write_disposition="merge"`** — instead of replacing the table, dlt upserts each row using the `primary_key`. Running the pipeline twice on the same data produces the same table: no duplicates.

**`dlt.current.resource_state()`** — a dict that dlt persists to Postgres after each successful load (in `wikipedia._dlt_pipeline_state`). It's how the pipeline remembers where it left off between runs. The cursor is stored as the latest `timestamp` string seen across all articles.

**`start >= end` guard** — the Wikimedia API rejects requests where the date range is zero or covers only part of a month. When the cursor has already reached the first of the current month, we return early before making any API calls.

**`end` capped at the first of the current month** — the API sometimes returns data for the ongoing (incomplete) month. If that timestamp were stored as the cursor, the next run would request a date range of a few days into the current month, which the API rejects. Capping `end` at `YYYY-MM-01` means we only ever store complete months in the cursor.

## When to use `--full-refresh`

```bash
python wikipedia_incremental.py --full-refresh
```

Use this when you add a new article to `ARTICLES`. Without it, the new article would only be fetched from the current cursor position forward — you'd be missing all its history. Full refresh re-fetches everything from the beginning and upserts into the existing table, so existing rows are updated and the new article's history is backfilled in one run.

## What's next

Both Wikipedia pipelines fetch from a single flat endpoint. The next tutorial — [Pegel Online](./pegel-online.md) — introduces a more realistic source: two separate resources (measurements and station metadata), a chunked API to handle large date ranges, and nested JSON that dlt automatically unpacks into a child table.
