# =============================================================================
# Streamlit - Python data apps
# =============================================================================
# There is no official Streamlit image. Docker Hub's `streamlit/streamlit`
# does not exist (checked: "object not found"), and upstream's own guide
# tells you to write a Dockerfile. So this one is ours, and it is thin:
# a slim Python plus the packages an app in this stack is likely to reach
# for.
#
# Why these packages and not fewer: an empty Streamlit can render text and
# nothing else. A data app here wants to read the shared PostgreSQL or a
# Parquet file and draw a chart, and installing that at runtime would mean
# every container start waits on PyPI. pandas, numpy, altair and pyarrow
# are already Streamlit's own dependencies — only duckdb, plotly and
# psycopg2 are added weight.
#
# Why git: the entrypoint clones the Forgejo workspace repo, which is how
# a user gets an app of their own onto this server without a deploy.
# =============================================================================

FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# Every version pinned. A floating `streamlit` would move the launcher's
# API out from under it — st.navigation is 1.36+, and the dict form used
# for sections is 1.37+.
RUN pip install --no-cache-dir \
    "streamlit==1.64.0" \
    "duckdb==1.5.5" \
    "plotly==7.1.0" \
    "psycopg2-binary==2.9.13"

# The launcher and the apps arrive as mounts, not as image layers, so an
# edit in the repo reaches the server on the next spin-up without a
# rebuild. This only creates the mount points.
RUN mkdir -p /srv/apps

WORKDIR /srv

EXPOSE 8080
