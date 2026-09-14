# =============================================================================
# MLflow tracking server — the official image plus the two drivers it omits
# =============================================================================
# `ghcr.io/mlflow/mlflow` ships MLflow, SQLAlchemy and alembic, and nothing to
# talk to a real backend with. Measured on v3.16.0:
#
#     mlflow           3.16.0
#     SQLAlchemy       2.0.52
#     alembic          1.19.1
#     psycopg2         FEHLT      <- needed for --backend-store-uri postgresql://
#     boto3            FEHLT      <- needed for --artifacts-destination s3://
#
# So the image as published can only run against SQLite and a local directory,
# which is exactly the configuration this stack does not want: neither would
# survive a teardown.
#
# Note the tag form. `ghcr.io/mlflow/mlflow:3.16.0` does not exist; upstream
# prefixes releases with `v`. Both architectures are published, so this builds
# on the x86 servers the project runs and on an Apple-Silicon laptop.
#
# When bumping: the version appears in THREE places that must move together —
# the FROM line here, `image:` in services.yaml, and the `:-` fallback in
# docker-compose.yml. `test_compose_fallbacks_match_the_declared_version`
# catches the last two against each other; nothing catches this one, so it is
# called out in docs/stacks/mlflow.md under Upgrading.
FROM ghcr.io/mlflow/mlflow:v3.16.0

# Pinned exactly, like every other custom image here. psycopg2-binary rather
# than psycopg2 because the image carries no build toolchain — the source
# distribution would need libpq-dev and a compiler.
RUN pip install --no-cache-dir \
    "psycopg2-binary==2.9.13" \
    "boto3==1.43.93"
