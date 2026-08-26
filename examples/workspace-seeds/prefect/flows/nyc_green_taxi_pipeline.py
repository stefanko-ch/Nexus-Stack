"""NYC Green-Taxi 2025 → R2 → DuckDB stats — Prefect-3-idiomatic seed.

This flow is the Prefect counterpart to the Kestra `r2-taxi-pipeline.yaml`
seed. Both ship by default with Nexus-Stack, both write into the same
`s3://<bucket>/nexus-tutorials/NYC/` R2 prefix, and both share the same
shape — download monthly NYC TLC parquets, upload to R2, run a DuckDB
stats query, log the result. The deliberate split:

  Kestra  → Yellow Taxi (`yellow_tripdata_2025-*.parquet`)
  Prefect → Green Taxi  (`green_tripdata_2025-*.parquet`)

Same TLC source, same R2 prefix, distinct file family — the two
seeded flows coexist without overwriting each other and let students
compare the two engines side-by-side on different-but-related data.

This file was seeded into your Forgejo workspace repo from
`nexus-stack/examples/workspace-seeds/prefect/flows/`
during Initial Setup. Edit it in Forgejo — the worker re-clones the
repo on every flow run via the `pull:` step in `prefect.yaml`, so
your changes take effect on the next "Run" without a re-spin.
Subsequent spin-ups will leave your edits untouched (seeding only
adds new files, it never overwrites).

NO `triggers:` block — by Nexus-Stack convention seeded example
flows must NEVER ship with a schedule, so a fresh student stack
doesn't burn through CloudFront's egress budget by firing every
5 minutes on N parallel installs. Run manually from the Prefect
UI's "Run" button.
"""

from __future__ import annotations

import os

import boto3
import botocore.config
import duckdb
import httpx
from prefect import flow, get_run_logger, task

CLOUDFRONT = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def _lit(value: object) -> str:
    """Render a value as a safely quoted SQL string literal.

    DuckDB's SET statements take no parameter placeholders — you cannot
    write ``SET s3_access_key_id = ?`` — so credentials and paths have
    to be inlined into the SQL text. That makes quoting this code's job:
    an apostrophe inside a value closes the string literal early, the
    statement fails with a syntax error, and the error message can carry
    a fragment of the value into the Prefect run log. Doubling the
    apostrophe is the SQL-standard escape.
    """
    return "'" + str(value).replace("'", "''") + "'"


@task(retries=2, retry_delay_seconds=10, log_prints=True)
def download_month(month: str) -> bytes:
    """Pull one Green-Taxi month from NYC TLC's CloudFront and return raw parquet bytes.

    Prefect retries the task up to TWO times on transient HTTP errors
    (CloudFront occasionally 5xx's during long sessions) — three total
    attempts including the initial one. Enough to clear flaky CDN
    behavior without masking real upstream outages.
    """
    url = f"{CLOUDFRONT}/green_tripdata_2025-{month}.parquet"
    print(f"[download] {url}")
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    print(f"[download] {url} → {len(resp.content) / (1024 * 1024):.1f} MB")
    return resp.content


@task(log_prints=True)
def upload_month(month: str, body: bytes) -> str:
    """Upload one month's parquet bytes into R2 under nexus-tutorials/NYC/.

    Returns the resulting object key so downstream tasks can chain on it
    deterministically. R2 credentials come from the prefect-worker
    container's env vars (the deploy pipeline writes R2_* into stacks/prefect/.env).
    """
    # `addressing_style="path"` is required for Cloudflare R2: without
    # it, botocore can fall back to virtual-host-style URLs
    # (`<bucket>.<account>.r2.cloudflarestorage.com`) which R2 rejects.
    # Documented in docs/tutorials/databricks/r2-datalake.md.
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        region_name="auto",
        config=botocore.config.Config(s3={"addressing_style": "path"}),
    )
    key = f"nexus-tutorials/NYC/green_tripdata_2025-{month}.parquet"
    s3.put_object(Bucket=os.environ["R2_BUCKET"], Key=key, Body=body)
    print(f"[upload]   s3://{os.environ['R2_BUCKET']}/{key} ({len(body)} bytes)")
    return key


@task(log_prints=True)
def aggregate_stats(months: list[str]) -> dict:
    """Run a DuckDB query over the EXACT set of green_tripdata parquets
    this flow-run uploaded (one path per month, not a wildcard) and
    return a summary dict.

    Originally this used a `green_tripdata_*.parquet` wildcard, which
    matched every file already on R2 — so a re-run with a smaller
    `months` set would still report stats for previously-uploaded
    months and the output wouldn't match what the user just asked
    for. Switched to an explicit list of `s3://...` paths matching
    the months argument so the result is consistent with the
    invocation.

    Reads via httpfs + the S3-compatible R2 endpoint — no
    intermediate copy.

    Note: Green-Taxi parquets use `lpep_pickup_datetime` /
    `lpep_dropoff_datetime` (Yellow uses `tpep_*`). If you adapt
    this flow to Yellow, update the column names accordingly.
    """
    bucket = os.environ["R2_BUCKET"]
    endpoint_host = os.environ["R2_ENDPOINT"].removeprefix("https://").removeprefix("http://")
    # Explicit per-month paths; DuckDB's read_parquet accepts a list
    # and unions them. Sort for stability (deterministic earliest/
    # latest in the result).
    paths = ", ".join(
        _lit(f"s3://{bucket}/nexus-tutorials/NYC/green_tripdata_2025-{m}.parquet")
        for m in sorted(set(months))
    )
    sql = f"""
        INSTALL httpfs;
        LOAD httpfs;
        SET s3_endpoint          = {_lit(endpoint_host)};
        SET s3_access_key_id     = {_lit(os.environ["R2_ACCESS_KEY"])};
        SET s3_secret_access_key = {_lit(os.environ["R2_SECRET_KEY"])};
        SET s3_url_style         = 'path';
        SET s3_use_ssl           = true;

        SELECT
            COUNT(*)                         AS total_trips,
            ROUND(AVG(trip_distance), 2)     AS avg_distance_mi,
            ROUND(AVG(total_amount), 2)      AS avg_fare_usd,
            ROUND(AVG(passenger_count), 2)   AS avg_passengers,
            MIN(lpep_pickup_datetime)        AS earliest_pickup,
            MAX(lpep_pickup_datetime)        AS latest_pickup
        FROM read_parquet([{paths}]);
    """
    con = duckdb.connect(":memory:")
    row = con.execute(sql).fetchone()
    con.close()
    return {
        "total_trips": row[0],
        "avg_distance_mi": row[1],
        "avg_fare_usd": row[2],
        "avg_passengers": row[3],
        "earliest_pickup": row[4],
        "latest_pickup": row[5],
    }


@flow(
    name="nyc-green-taxi-pipeline",
    description=(
        "Bootstrap + analyse the NYC Green-Taxi 2025 dataset on R2 (Prefect "
        "version of the Kestra Yellow-Taxi tutorial). "
        "Both stacks ship a seeded flow on different TLC datasets so the two "
        "engines can be compared side-by-side without overwriting each "
        "other's R2 output."
    ),
    log_prints=True,
)
def nyc_green_taxi_pipeline(months: list[str] | None = None) -> dict:
    """Default 2 months (Jan + Feb 2025) keeps each Run lightweight on a
    student stack. Pass `months=["01","02",...,"12"]` to widen.

    Sequential per-month task submission (not `.submit()` parallel) is
    deliberate: each parquet is ~60 MB and the worker has 1 GB RAM by
    default. Parallel-12 would risk OOM. Worst-case wall time on a fresh
    run with 2 months: ~30 s.
    """
    months = months or ["01", "02"]
    log = get_run_logger()

    # Upfront R2 precondition check. The render path
    # (nexus_deploy.service_env._render_prefect) writes the four R2_*
    # env vars to stacks/prefect/.env unconditionally, but with empty
    # values when the optional R2 datalake isn't configured in
    # OpenTofu (the r2_data_* fields on NexusConfig). Without this
    # guard, the first `upload_month` task would crash deep inside
    # boto3 (the boto3 S3 client is constructed there with the
    # R2_* env vars) with a confusing 'invalid endpoint URL' / SSL
    # error; surfacing the missing-R2 case here gives the operator
    # an actionable next step instead. (`download_month` reads from
    # CloudFront and doesn't touch R2 at all, so it would succeed
    # even with R2_* unset — the failure point is the upload.)
    missing = [
        var
        for var in ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET")
        if not os.environ.get(var)
    ]
    if missing:
        raise RuntimeError(
            f"R2 datalake not configured: missing {', '.join(missing)}. "
            "Set the r2_data_endpoint / r2_data_access_key / r2_data_secret_key / "
            "r2_data_bucket fields in your Tofu config and re-run "
            "`gh workflow run spin-up.yml` so the prefect-worker container "
            "picks up the values via stacks/prefect/.env.",
        )

    for m in months:
        body = download_month(m)
        upload_month(m, body)

    stats = aggregate_stats(months)
    log.info(
        "─── NYC Green-Taxi 2025 — Quick-Stats ──────────────────\n"
        "  Trips:           %s\n"
        "  Avg distance:    %s mi\n"
        "  Avg fare:        $ %s\n"
        "  Avg passengers:  %s\n"
        "  Date range:      %s → %s\n"
        "──────────────────────────────────────────────────────",
        stats["total_trips"],
        stats["avg_distance_mi"],
        stats["avg_fare_usd"],
        stats["avg_passengers"],
        stats["earliest_pickup"],
        stats["latest_pickup"],
    )
    return stats


if __name__ == "__main__":
    # Local-dev convenience: `python nyc_green_taxi_pipeline.py` runs the flow
    # without going through a worker. Requires R2_* env vars to be set in your
    # shell. The Prefect server still records the run if PREFECT_API_URL points
    # at a server.
    nyc_green_taxi_pipeline()
