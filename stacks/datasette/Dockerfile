# =============================================================================
# Datasette - multi-arch build
# =============================================================================
# The official datasetteproject/datasette image is amd64 only. Built from
# python:slim with pip, the image is arch-correct on amd64 and arm64.
# sqlite-utils comes along so CSV and JSON can be loaded into a database
# from inside the container.
# =============================================================================

FROM python:3.12-slim

RUN pip install --no-cache-dir \
    "datasette==0.65.5" \
    "sqlite-utils==4.2.1"

RUN useradd --uid 1000 --create-home datasette \
    && mkdir /data \
    && chown datasette:datasette /data

USER datasette
WORKDIR /data

EXPOSE 8001

# Configuration-directory mode: every *.db file in /data is served. The
# directory is read on start, so a new file appears after a restart.
CMD ["datasette", "serve", "/data", "--host", "0.0.0.0", "--port", "8001"]
