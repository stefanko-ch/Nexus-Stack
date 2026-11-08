---
title: "Read and write R2 from a Databricks notebook"
description: "Use the synced Nexus-Stack R2 credentials from the nexus Databricks secret scope to read and write Parquet files"
order: 1
---

# Read and write R2 from a Databricks notebook

Nexus-Stack's external data-lake lives in Cloudflare R2. This tutorial shows how to read from and write to that bucket from a Databricks notebook, using the credentials that the Control Plane already mirrors into your `nexus` secret scope.

## Where R2 fits in Nexus-Stack

R2 is Nexus's **external-facing** S3 bridge. It's the one S3-compatible endpoint that is reachable from the public internet, which makes it the only Nexus storage that SaaS tools like Databricks can plug into directly.

Internal Nexus services do **not** use R2 by default. The shipped config splits internal storage in two directions:

- **Spark, Jupyter, LakeFS, Filestash** — S3-compatible writes go to **Hetzner Object Storage** via its public S3 endpoint. The server lives in a Hetzner datacenter, so this traffic stays inside Hetzner's network — low latency, no Cloudflare egress, no tunnel hop.
- **MinIO, Garage, SeaweedFS** — self-contained object stores that keep their data on local Docker volumes inside the Nexus server. Same `app-network`, no external dependency.

R2 is layered on top of this for the **external** use case only (Databricks, other SaaS tools that need to reach the data lake from the public internet). So:

- **You want Databricks to read Parquet files from your Nexus data lake → R2** (this tutorial).
- **You want Jupyter-in-Nexus to write Parquet files for a Nexus-internal pipeline → use LakeFS or Hetzner Object Storage, not R2** (see [docs/stacks/lakefs](/docs/stacks/lakefs/)).

The R2 bucket **persists across `destroy-all`** — Cloudflare side lives independently of the Hetzner server, and the teardown workflow explicitly preserves both the bucket and the API token. Your Parquet files survive a stack reset.

## Prerequisites

- Nexus-Stack deployed (spin-up successful, Infisical running).
- Databricks workspace connected on the Control Plane [Integrations page](/docs/guides/user-guides/integrations/) (host + personal access token saved).
- **Sync Now** pressed on the [Secrets page](/docs/guides/user-guides/secrets/) at least once. After that, `dbutils.secrets.list("nexus")` from a Databricks notebook should include these keys:
  - `r2-datalake/R2_ENDPOINT`
  - `r2-datalake/R2_ACCESS_KEY`
  - `r2-datalake/R2_SECRET_KEY`
  - `r2-datalake/R2_BUCKET`
  - `r2-datalake/R2_ACCOUNT_ID`
  - `r2-datalake/R2_DATABRICKS_URL`
- A Databricks cluster (Free Edition works) attached to your notebook.

If all keys are missing, it's one of two things:
1. **Spin-up didn't see R2 creds.** Check that `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_DATA_BUCKET` exist in your GitHub repo's Actions Secrets. If not, re-run `gh workflow run setup-control-plane.yaml` with `GH_SECRETS_TOKEN` configured — it auto-populates them.
2. **Sync Now wasn't pressed after the last spin-up.** Go to Secrets → Databricks panel → click the button.

If only `R2_ACCOUNT_ID` and `R2_DATABRICKS_URL` are missing:

- **The stack has not been spun up since they were added.** Sync Now only copies what is already in Infisical, and the spin-up is what writes these two keys. Run a spin-up, then press Sync Now.
- **`R2_ENDPOINT` is not of the form `https://<32-hex account ID>.r2.cloudflarestorage.com`.** The two keys are derived from it and left out otherwise. The endpoint is built from the `CLOUDFLARE_ACCOUNT_ID` secret, so check that one.

## What the keys mean

| Key | Example value | Purpose |
|---|---|---|
| `r2-datalake/R2_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` | S3-compatible API endpoint |
| `r2-datalake/R2_ACCESS_KEY` | Token ID (long hex string) | `AWS_ACCESS_KEY_ID` / `fs.s3a.access.key` |
| `r2-datalake/R2_SECRET_KEY` | SHA-256 of the raw Cloudflare token | `AWS_SECRET_ACCESS_KEY` / `fs.s3a.secret.key` |
| `r2-datalake/R2_BUCKET` | `nexus-<domain-slug>-data` | Bucket name (no `s3://` prefix) |
| `r2-datalake/R2_ACCOUNT_ID` | 32-character hex string | Cloudflare account ID, the host part of `R2_ENDPOINT` |
| `r2-datalake/R2_DATABRICKS_URL` | `r2://<bucket>@<account-id>.r2.cloudflarestorage.com/` | URL of a Unity Catalog external location |

The last two hold nothing new. They are the endpoint and bucket in the shape the Databricks forms ask for, so they can be copied instead of assembled. They are only written when the endpoint is an R2 host.

The `R2_SECRET_KEY` being a SHA-256 hash of the Cloudflare token (rather than the token itself) is [Cloudflare's documented convention](https://developers.cloudflare.com/r2/api/tokens/#get-s3-api-credentials-from-an-api-token) for S3-compatible auth. Any S3 client treats it as a normal secret access key; you never do the hashing yourself.

## Path 0: Unity Catalog external location

Unity Catalog can govern the bucket itself: one storage credential and one external location, created once, and every notebook reads `r2://` paths without setting any keys. Databricks supports this for R2 natively. The two forms ask for these values, all in the Infisical folder `r2-datalake`:

**Storage credential** (Catalog Explorer, under External data), type **Cloudflare API Token**:

| Form field | Infisical key |
|---|---|
| Account ID | `R2_ACCOUNT_ID` |
| Access key ID | `R2_ACCESS_KEY` |
| Secret access key | `R2_SECRET_KEY` |

**External location**, storage type **R2**:

| Form field | Value |
|---|---|
| URL | `R2_DATABRICKS_URL` |
| Storage credential | the credential from the step above |

Then grant access to the group that should use the bucket, and read it. The examples call the location `r2` and the group `r2-users`; use your own names. Grant `WRITE FILES` only to those who write, since `account users` would give every user of the account the whole bucket:

```sql
GRANT READ FILES ON EXTERNAL LOCATION r2 TO `r2-users`;
GRANT WRITE FILES ON EXTERNAL LOCATION r2 TO `r2-users`;  -- only if they write
```

```python
url = dbutils.secrets.get("nexus", "r2-datalake/R2_DATABRICKS_URL")
display(dbutils.fs.ls(url))
```

The URL ends in `/`, so append a path without a leading slash: `f"{url}tutorial/sample.parquet"`. Creating credentials and external locations needs the `CREATE STORAGE CREDENTIAL` and `CREATE EXTERNAL LOCATION` privileges on the metastore. When you do not have them, use Path 1, which needs neither.

## Path 1: PySpark via s3a:// (no Unity Catalog setup)

This is the workflow you want for anything Delta-table-shaped — Spark reads and writes `s3a://bucket/path` URIs natively, checkpoints work, and you can use the full DataFrame API.

### Load credentials

```python
ENDPOINT    = dbutils.secrets.get("nexus", "r2-datalake/R2_ENDPOINT")
ACCESS_KEY  = dbutils.secrets.get("nexus", "r2-datalake/R2_ACCESS_KEY")
SECRET_KEY  = dbutils.secrets.get("nexus", "r2-datalake/R2_SECRET_KEY")
BUCKET      = dbutils.secrets.get("nexus", "r2-datalake/R2_BUCKET")
```

Don't `print(...)` any of these values — Databricks redacts secret-scope results to `[REDACTED]` regardless of what's actually stored, so the print isn't a useful verification step and is a bad habit to build. If you need to confirm the bucket name, check the Control Plane Secrets page or the Cloudflare R2 dashboard, or just proceed with the write below and let a successful `list_objects` / `count()` be the confirmation.

### Configure Hadoop S3A

```python
hconf = spark._jsc.hadoopConfiguration()
hconf.set("fs.s3a.endpoint",               ENDPOINT)
hconf.set("fs.s3a.access.key",             ACCESS_KEY)
hconf.set("fs.s3a.secret.key",             SECRET_KEY)
hconf.set("fs.s3a.path.style.access",      "true")   # required for R2
hconf.set("fs.s3a.region",                 "auto")   # R2 ignores region, but Hadoop wants one
hconf.set("fs.s3a.aws.credentials.provider",
          "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
```

Three R2-specific points:

- **`path.style.access = true` is not optional.** R2 does not support virtual-host-style addressing (`<bucket>.<account>.r2.cloudflarestorage.com`). You will get `UnknownHostException` without it.
- **`region = auto`** — R2 is globally distributed, but Hadoop's AWS SDK refuses to start if no region is configured. `auto` is accepted by the SDK and ignored by R2, which is what you want.
- **`SimpleAWSCredentialsProvider`** is the one provider that reads the access key / secret key from Hadoop config directly. The default chain walks AWS instance metadata and IAM roles, neither of which exist on a Databricks cluster reading R2.

### Write and read a Parquet file

```python
path = f"s3a://{BUCKET}/tutorial/sample.parquet"

# Write
(spark.range(100)
      .withColumnRenamed("id", "n")
      .write.mode("overwrite")
      .parquet(path))

# Read back
df = spark.read.parquet(path)
print(f"Row count: {df.count()}")   # 100
df.show(5)
```

Expected output:

```
Row count: 100
+---+
|  n|
+---+
|  0|
|  1|
|  2|
|  3|
|  4|
+---+
```

If you see `Row count: 100` and five rows, your Databricks cluster is successfully reading and writing R2 through the S3A connector. Everything else — Delta tables, partitioning, MERGE INTO, structured streaming sinks — works the same way from here; the `s3a://` URI is just a Hadoop path.

## Path 2: boto3 (recommended for single-file operations)

Good for quick uploads, bucket listings, or one-off object inspection. Uses the same credentials.

```python
import boto3
from botocore.config import Config

# Force path-style addressing — botocore picks virtual-host-style by default
# on some versions, which on R2 can fail or produce the wrong URL shape
# (`<bucket>.<account>.r2.cloudflarestorage.com`). The path-style form
# (`<account>.r2.cloudflarestorage.com/<bucket>/…`) is what R2 prefers and
# is required for consistent behaviour across botocore releases.
s3 = boto3.client(
    "s3",
    endpoint_url          = dbutils.secrets.get("nexus", "r2-datalake/R2_ENDPOINT"),
    aws_access_key_id     = dbutils.secrets.get("nexus", "r2-datalake/R2_ACCESS_KEY"),
    aws_secret_access_key = dbutils.secrets.get("nexus", "r2-datalake/R2_SECRET_KEY"),
    region_name           = "auto",
    config                = Config(s3={"addressing_style": "path"}),
)
BUCKET = dbutils.secrets.get("nexus", "r2-datalake/R2_BUCKET")

# Upload a small in-memory file
s3.put_object(Bucket=BUCKET, Key="tutorial/hello.txt", Body=b"hello from databricks")

# List what's in the tutorial/ prefix
for obj in s3.list_objects_v2(Bucket=BUCKET, Prefix="tutorial/").get("Contents", []):
    print(f"  {obj['Key']:<40} {obj['Size']:>8} bytes")

# Read it back
resp = s3.get_object(Bucket=BUCKET, Key="tutorial/hello.txt")
print(resp["Body"].read().decode())   # "hello from databricks"
```

Expected output:

```
  tutorial/hello.txt                         22 bytes
  tutorial/sample.parquet/_SUCCESS            0 bytes
  tutorial/sample.parquet/part-00000-...    870 bytes
  ...
hello from databricks
```

You can see both the `boto3` upload and the Parquet parts from Path 1 sitting in the same prefix.

## Path 3: dbutils.fs.mount — avoid

Mounts technically work against R2 via `s3a://`, but Databricks has been moving away from them for years in favour of Unity Catalog External Locations. Two reasons to skip mounts:

- They're cluster-scoped, not workspace-scoped; students on different clusters need to mount separately.
- A mount stores the credentials in the cluster's internal state — rotating the R2 token requires unmounting and remounting everywhere.

Just use `s3a://` directly. Everything you can do with a mount, you can do with the full URI.

## Common errors

**`UnknownHostException: <bucket>.<account-id>.r2.cloudflarestorage.com`**
`fs.s3a.path.style.access` is not `true`. Fix the Hadoop config.

**`403 SignatureDoesNotMatch`**
Either the wrong secret key (check you're reading `R2_SECRET_KEY`, not a raw Cloudflare token), or the Hadoop region isn't set — Spark silently fails signing when region is empty. Set `fs.s3a.region = auto`.

**`NoSuchBucket: nexus-<domain-slug>-data`**
Bucket-name format uses dashes only — dots in the domain get replaced by dashes (`stefanko.ch` → `stefanko-ch`). Confirm the value stored in the `R2_BUCKET` secret matches what exists in Cloudflare Dashboard → R2 → Buckets.

**`SocketTimeoutException` or `connection refused`**
Databricks Classic compute in some regions has egress restrictions to `*.r2.cloudflarestorage.com`. Switch to Serverless compute (default on Free Edition), or check your workspace's network policy.

**`The AWS Access Key Id you provided does not exist in our records`**
You've probably picked up the wrong secret — double-check you're reading from `r2-datalake/*` and not from the legacy top-level keys. The sync button on the Secrets page cleans those up automatically; if you haven't clicked Sync since upgrading past v0.51.9, do that first.

## Hooking up to a Nexus-side producer

The tutorial above is self-contained — `spark.range(100)` is your "data source." For a real workflow, you probably want Nexus-side tools to land data in R2 so Databricks can pick it up. Two light patterns:

- **Python script inside [code-server](/docs/tutorials/code-server/) using `boto3`**, reading the same keys from Infisical (`/r2-datalake` folder), writing Parquet to `s3://<R2_BUCKET>/incoming/…` (substitute the real bucket name from the `R2_BUCKET` secret — same `nexus-<domain-slug>-data` format used throughout the tutorial). Databricks polls that prefix on a schedule.
- **[Redpanda-Connect](/docs/tutorials/redpanda-connect/)** with an `aws_s3` output pointed at the R2 endpoint. Same credentials, streams Kafka events straight to R2 objects.

Neither is in scope for this tutorial, but both are natural next steps once you've confirmed the Databricks → R2 round-trip works.

## Next steps

- [Sync Infisical secrets into Databricks](/docs/guides/user-guides/integrations/) — the sync mechanism this tutorial relies on, with screenshots of the Integrations + Secrets pages.
- [Spark Structured Streaming → Bronze Delta](/docs/tutorials/spark/bronze-delta/) — now that R2 works, you can point the checkpoint and sink locations at `s3a://<bucket>/…` for a real medallion pipeline.
