# =============================================================================
# ZenML server - built from the pinned PyPI release
# =============================================================================
# The published zenmldocker/zenml-server images are amd64 only. This
# installs the same release, zenml[server]==0.98.0, on python:slim, which
# builds for amd64 and arm64. It follows the server stage of upstream's
# docker/base.Dockerfile: a non-root user, the config under
# /zenml/.zenconfig, uvicorn behind a proxy. Upstream also installs the
# extras for cloud secret stores and orchestrators (AWS, GCP, Azure); they
# are left out here, as the server uses its own SQL store.
# =============================================================================

FROM python:3.12.13-slim

ARG ZENML_VERSION=0.98.0

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ZENML_CONTAINER=1 \
    ZENML_CONFIG_PATH=/zenml/.zenconfig \
    ZENML_DEBUG=false \
    ZENML_ANALYTICS_OPT_IN=false

RUN pip install "zenml[server]==${ZENML_VERSION}"

RUN groupadd --gid 1000 zenml \
    && useradd --uid 1000 --gid 1000 --create-home zenml \
    && mkdir -p /zenml/.zenconfig/local_stores/default_zen_store \
    && chown -R 1000:1000 /zenml

WORKDIR /zenml
USER zenml
EXPOSE 8080

CMD ["uvicorn", "zenml.zen_server.zen_server_api:app", "--no-server-header", "--proxy-headers", "--forwarded-allow-ips", "*", "--port", "8080", "--host", "0.0.0.0"]
