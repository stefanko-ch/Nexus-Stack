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

USER coder

# Install JupyterLab via uv (provides the jupyter CLI as a system-wide tool)
RUN uv tool install jupyterlab==4.3.6

# Add uv tool bin to PATH (covers JupyterLab + future uv-tool installs)
ENV PATH="/home/coder/.local/bin:${PATH}"

# Create nexus-venv with dbt + notebook tooling pre-installed.
#
# dbt stack (pinned 1.9.x — matches stefanko-ch/dbt_codespace_demo template):
# - dbt-core: the dbt engine
# - dbt-postgres: adapter to connect to the Nexus-Stack postgres stack
# - dbt-duckdb: adapter for local-file DuckDB targets
#
# Notebook tooling (layered into the same venv so dbt models can be
# inspected from in-notebook SQL cells without env-switching):
# - jupyter / jupysql: SQL magic cells (%sql, %%sql) against any adapter
# - polars / plotly: fast dataframes + visualisation
# - duckdb: Python bindings (separate from the CLI binary above)
#
# Naming the venv "nexus-venv" (not the demo's ".venv") so students recognise
# it as the Nexus-Stack-provided environment, distinct from any per-project
# .venv they may create in their dbt workspace.
RUN uv venv /home/coder/nexus-venv && \
    uv pip install --python /home/coder/nexus-venv/bin/python --no-cache-dir \
      'dbt-core>=1.9,<1.10' \
      'dbt-postgres>=1.9,<1.10' \
      'dbt-duckdb>=1.9,<1.10' \
      jupyter \
      jupysql \
      polars \
      plotly \
      duckdb

# Auto-activate nexus-venv in every interactive shell opened inside the
# code-server terminal. Students get a ready-to-use `dbt` + `duckdb` prompt
# without any setup step.
RUN { \
      echo ''; \
      echo '# Auto-activate Nexus-Stack pre-installed dbt + DuckDB venv'; \
      echo 'if [ -f /home/coder/nexus-venv/bin/activate ]; then'; \
      echo '  . /home/coder/nexus-venv/bin/activate'; \
      echo 'fi'; \
    } >> /home/coder/.bashrc
