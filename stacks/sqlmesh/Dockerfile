# =============================================================================
# SQLMesh - multi-arch build
# =============================================================================
# SQLMesh publishes no Docker image. Built from python:slim with pip, the
# image is arch-correct on amd64 and arm64. The `web` extra brings the
# browser UI. Projects run on the bundled DuckDB; other engines' extras
# (postgres needs a compiler and pg_config) are left out of the image.
# =============================================================================

FROM python:3.12-slim

RUN pip install --no-cache-dir "sqlmesh[web]==0.236.4"

RUN useradd --uid 1000 --create-home sqlmesh \
    && mkdir /project \
    && chown sqlmesh:sqlmesh /project

USER sqlmesh
WORKDIR /project

EXPOSE 8000

# An empty /project becomes the SQLMesh example project on DuckDB, so the
# UI has something to show on first start. An existing project is left
# alone.
CMD ["sh", "-c", "if [ ! -e config.yaml ] && [ ! -e config.py ]; then sqlmesh init duckdb; fi; exec sqlmesh ui --host 0.0.0.0 --port 8000"]
