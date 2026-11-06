# =============================================================================
# Dagster - Custom ARM64-compatible build
# =============================================================================
# Official Dagster doesn't publish pre-built Docker images, so we build our
# own using Python 3.11 base image and install via pip.
# =============================================================================

FROM python:3.11-slim

# Install system dependencies required for PostgreSQL driver
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Dagster with webserver and PostgreSQL support.
#
# sqlalchemy is pinned to the 2.0 line because this image is rebuilt on
# every spin-up and nothing else holds it there. SQLAlchemy 2.1 maps a
# bare postgresql:// URL to psycopg 3, while dagster-postgres ships only
# psycopg2-binary, so both dagster containers died on start with
# "No module named 'psycopg'" once 2.1.8 reached PyPI.
RUN pip install --no-cache-dir \
    dagster==1.12.21 \
    dagster-webserver==1.12.21 \
    dagster-postgres==0.28.21 \
    sqlalchemy==2.0.57

# Create Dagster home directory
ENV DAGSTER_HOME=/opt/dagster/dagster_home
RUN mkdir -p $DAGSTER_HOME

WORKDIR $DAGSTER_HOME

EXPOSE 3000

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000"]
