FROM codercom/code-server:latest

USER root

# System packages:
# - python3 / python3-venv / python3-pip: required for the nexus-venv (dbt) below
# - postgresql-client: psql CLI for testing dbt-postgres adapter connections
#   against the Nexus-Stack postgres stack (no postgres SERVER here — that's
#   a separate stack)
# - curl, ca-certificates, unzip: needed for uv + DuckDB CLI downloads
# - git: re-asserted (already in the base image, harmless if redundant)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      postgresql-client \
      curl ca-certificates unzip git && \
    rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager) - pinned version
RUN curl -LsSf https://astral.sh/uv/0.6.12/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Install DuckDB CLI (latest stable from GitHub releases, multi-arch).
# Pattern mirrors stefanko-ch/dbt_codespace_demo's devcontainer Dockerfile.
#
# NOTE: DuckDB has a fast release cadence (often monthly minor releases).
# The ":latest" download URL means every image rebuild picks up whatever
# version is current — convenient for staying close to upstream, but means
# students may see a different DuckDB version after a fresh spin-up than
# they had before. If you need reproducibility across rebuilds, pin to a
# specific tag (e.g. .../releases/download/v1.1.3/duckdb_cli-linux-amd64.zip).
RUN ARCH="$(uname -m)" && \
    case "$ARCH" in \
      x86_64)        CLI_URL="https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip" ;; \
      aarch64|arm64) CLI_URL="https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-aarch64.zip" ;; \
      *) echo "Unsupported arch $ARCH for DuckDB CLI" && exit 1 ;; \
    esac && \
    curl -fsSL "$CLI_URL" -o /tmp/duckdb.zip && \
    unzip -o /tmp/duckdb.zip -d /usr/local/bin && \
    rm /tmp/duckdb.zip && \
    chmod +x /usr/local/bin/duckdb && \
    duckdb --version

# Create nexus-venv with dbt + notebook tooling pre-installed.
#
# LOCATION: /opt/nexus-venv (NOT /home/coder/.nexus-venv).
# Rationale: docker-compose.yml mounts code-server-data:/home/coder, which
# means anything baked into the image at /home/coder/<X> is MASKED by the
# volume on every container start. Existing volumes never see new venv
# content from a rebuilt image; users only ever get whatever the volume
# was first-initialised with. Putting the venv at /opt/nexus-venv —
# outside the volume mount — guarantees every rebuild's venv is the one
# students see, regardless of when the code-server-data volume was first
# created.
#
# All packages UNPINNED — every image rebuild pulls the latest from PyPI.
# Trade-off vs. pinning (e.g. 'dbt-core>=1.9,<1.10' as in
# stefanko-ch/dbt_codespace_demo): stays current with security fixes and
# new features, but new minor/major versions may introduce breaking changes
# mid-semester if you trigger a rebuild during a course run. Operator's
# pick — add explicit version constraints if you need stability for a
# specific semester.
#
# dbt stack — adapters chosen to match the data-services Nexus-Stack
# ships as stacks (so students can model against any of them without
# leaving the platform):
# - dbt-core: the dbt engine
# - dbt-postgres: adapter for the Nexus-Stack postgres stack
# - dbt-duckdb: adapter for local-file DuckDB targets
# - dbt-clickhouse: adapter for the Nexus-Stack clickhouse stack
#   (official clickhouse/clickhouse-server image)
# - dbt-spark: installed for users who connect to an EXTERNAL Spark
#   cluster (Thrift / ODBC / session modes). NOT pre-wired to the
#   Nexus-Stack spark stack: that stack exposes Spark Connect
#   (sc://spark-connect:15002, used by PySpark/Marimo), but dbt-spark
#   does not support Spark Connect. The stack also doesn't run a Hive
#   Thrift Server, and this image deliberately omits local PySpark/JDK,
#   so 'session' mode needs extra setup too. There is no out-of-the-
#   box dbt path to data that lives only on the Nexus-Stack Spark
#   stack — for SQL workloads against other in-stack data (postgres,
#   clickhouse, DuckDB files), use the matching adapter directly.
# - dbt-trino: adapter for the Nexus-Stack trino stack (official
#   trinodb/trino image; catalogs: clickhouse + postgresql)
# - dbt-databricks: adapter only. The Nexus-Stack Databricks
#   integration (Control-Plane KV + /api/databricks-sync) pushes
#   Infisical secrets INTO a Databricks scope — it does NOT inject
#   databricks_host/token into code-server (or any local stack). To
#   use dbt-databricks here, save host + token in the Control Plane's
#   Databricks page, then add them to ~/.dbt/profiles.yml manually
#   (copy from the Control Plane's KV view).
#
# Intentionally NOT installed (operators who need them can layer into
# a per-project venv):
# - dbt-bigquery / dbt-snowflake / dbt-redshift: cloud-only, no
#   Nexus-Stack equivalent
# - dbt-fabric / dbt-sqlserver: Azure / Microsoft, out of scope for a
#   self-hosted classroom
# - dbt-athena: AWS-specific, out of scope
#
# Notebook tooling (layered into the same venv so dbt models can be
# inspected from in-notebook SQL cells without env-switching):
# - jupyterlab: full JupyterLab UI (the `jupyter lab` CLI)
# - jupysql: SQL magic cells (%sql, %%sql) against any adapter
# - polars / plotly: fast dataframes + visualisation
# - duckdb: Python bindings (separate from the CLI binary above)
RUN uv venv /opt/nexus-venv && \
    uv pip install --python /opt/nexus-venv/bin/python --no-cache-dir \
      dbt-core \
      dbt-postgres \
      dbt-duckdb \
      dbt-clickhouse \
      dbt-spark \
      dbt-trino \
      dbt-databricks \
      jupyterlab \
      jupysql \
      polars \
      plotly \
      duckdb && \
    chown -R coder:coder /opt/nexus-venv

# Auto-activate nexus-venv via /etc/bash.bashrc (system-wide, IMAGE-BAKED).
# Bash sources /etc/bash.bashrc for every interactive non-login shell —
# including the terminal inside code-server. Unlike /home/coder/.bashrc
# (which lives in the volume-masked /home/coder), /etc/bash.bashrc is
# always the one shipped with the image, so updates here actually take
# effect on the next container restart even for existing
# code-server-data volumes.
RUN { \
      echo ''; \
      echo '# Auto-activate Nexus-Stack pre-installed dbt + notebook venv'; \
      echo '# (image-baked at /opt/nexus-venv; survives volume-mount masking)'; \
      echo 'if [ -f /opt/nexus-venv/bin/activate ]; then'; \
      echo '  . /opt/nexus-venv/bin/activate'; \
      echo 'fi'; \
    } >> /etc/bash.bashrc

USER coder

# Keep uv-tool's local bin on PATH for any user-level uv-tool installs
# they may do later (the venv at /opt/nexus-venv prepends its own bin
# at activation time, so it wins over this PATH entry).
ENV PATH="/home/coder/.local/bin:${PATH}"
