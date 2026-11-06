# =============================================================================
# SQLMesh - multi-arch build
# =============================================================================
# SQLMesh publishes no Docker image. Built from python:slim with pip, the
# image is arch-correct on amd64 and arm64. The `web` extra brings the
# browser UI. Projects run on the bundled DuckDB by default. PostgreSQL
# works too: psycopg2-binary provides the psycopg2 module SQLMesh's postgres
# engine imports, without the compiler and pg_config the `postgres` extra's
# source build of psycopg2 would need.
# =============================================================================

FROM python:3.12-slim

RUN pip install --no-cache-dir "sqlmesh[web]==0.236.4" "psycopg2-binary==2.9.13"

RUN useradd --uid 1000 --create-home sqlmesh \
    && mkdir /project \
    && chown sqlmesh:sqlmesh /project

USER sqlmesh
WORKDIR /project

EXPOSE 8000

# An empty /project becomes the SQLMesh example project on DuckDB, so the
# UI has something to show on first start. An existing project is left
# alone. A failed init stops the container instead of starting the UI on a
# half-written project; restart: unless-stopped then retries it.
CMD ["sh", "-c", "set -e; if [ ! -e config.yaml ] && [ ! -e config.py ]; then sqlmesh init duckdb; fi; exec sqlmesh ui --host 0.0.0.0 --port 8000"]
