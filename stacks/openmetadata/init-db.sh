#!/bin/bash
# =============================================================================
# OpenMetadata - Airflow Database Initialization
# =============================================================================
# Creates the additional airflow_db database and nexus-airflow user required
# by the OpenMetadata Ingestion (Airflow) container.
# This script is mounted to /docker-entrypoint-initdb.d/ and runs automatically
# on first PostgreSQL startup.
# =============================================================================
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER "nexus-airflow" WITH PASSWORD '${OPENMETADATA_AIRFLOW_PASSWORD}';
    CREATE DATABASE airflow_db OWNER "nexus-airflow";
    GRANT ALL PRIVILEGES ON DATABASE airflow_db TO "nexus-airflow";
EOSQL
