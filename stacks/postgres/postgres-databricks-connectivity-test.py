# Databricks notebook source
# MAGIC %md
# MAGIC # PostgreSQL Connectivity Test
# MAGIC
# MAGIC Tests external TCP access to PostgreSQL via opened firewall port.
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Firewall rule for PostgreSQL port 5432 enabled in Control Plane
# MAGIC - Infrastructure deployed with Spin Up
# MAGIC - PostgreSQL password available in Infisical

# COMMAND ----------

# Configuration widgets
dbutils.widgets.text("domain", "your-domain.com", "Nexus-Stack Domain")
dbutils.widgets.text("password", "", "PostgreSQL Password (from Infisical)")
dbutils.widgets.text("user", "", "Database User (from Infisical)")

# COMMAND ----------

DOMAIN = dbutils.widgets.get("domain")
PASSWORD = dbutils.widgets.get("password")
USER = dbutils.widgets.get("user")

PG_HOST = f"postgres.{DOMAIN}"
PG_PORT = "5432"

print(f"Testing PostgreSQL at: {PG_HOST}:{PG_PORT}")
print(f"User: {USER}")

if not USER or not PASSWORD:
    dbutils.notebook.exit("Error: Username and password required. Get them from Infisical.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install psycopg2 library

# COMMAND ----------

%pip install psycopg2-binary

# COMMAND ----------

import psycopg2
from psycopg2 import sql
from datetime import datetime

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Test Connection to PostgreSQL

# COMMAND ----------

try:
    print(f"Connecting to {PG_HOST}:{PG_PORT}...")
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=USER,
        password=PASSWORD,
        database="postgres",
        connect_timeout=10
    )

    cur = conn.cursor()

    # Get PostgreSQL version
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"✅ Successfully connected to PostgreSQL")
    print(f"   Version: {version.split(',')[0]}")

    # Get current database
    cur.execute("SELECT current_database();")
    db = cur.fetchone()[0]
    print(f"   Database: {db}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Connection failed!")
    print(f"   Error: {type(e).__name__}: {str(e)}")
    print(f"\nTroubleshooting:")
    print(f"   1. Verify firewall rule for port 5432 is enabled in Control Plane")
    print(f"   2. Check credentials in Infisical (POSTGRES_USERNAME, POSTGRES_PASSWORD)")
    print(f"   3. Verify domain is correct: {PG_HOST}")
    print(f"   4. Ensure PostgreSQL is running: Check server status")
    import traceback
    print(f"\nFull error details:")
    traceback.print_exc()
    dbutils.notebook.exit(f"Connection test failed: {str(e)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create Test Table

# COMMAND ----------

try:
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=USER,
        password=PASSWORD,
        database="postgres"
    )
    cur = conn.cursor()

    # Create test table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_databricks (
            id SERIAL PRIMARY KEY,
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    print("✅ Test table 'test_databricks' created")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Table creation failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Insert Test Data

# COMMAND ----------

try:
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=USER,
        password=PASSWORD,
        database="postgres"
    )
    cur = conn.cursor()

    # Insert test records
    test_messages = [
        "Test from Databricks",
        "Firewall test successful",
        "External TCP access works"
    ]

    for msg in test_messages:
        cur.execute(
            "INSERT INTO test_databricks (message) VALUES (%s) RETURNING id",
            (msg,)
        )
        row_id = cur.fetchone()[0]
        print(f"✅ Inserted row {row_id}: {msg}")

    conn.commit()
    print(f"\n✅ Successfully inserted {len(test_messages)} rows")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Insert failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Query Test Data

# COMMAND ----------

try:
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=USER,
        password=PASSWORD,
        database="postgres"
    )
    cur = conn.cursor()

    # Query all test records
    cur.execute("SELECT id, message, timestamp FROM test_databricks ORDER BY id")
    rows = cur.fetchall()

    print("✅ Retrieved test data:")
    for row in rows:
        print(f"   ID {row[0]}: {row[1]} (at {row[2]})")

    print(f"\n✅ Successfully queried {len(rows)} rows")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Query failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Cleanup Test Table

# COMMAND ----------

try:
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=USER,
        password=PASSWORD,
        database="postgres"
    )
    cur = conn.cursor()

    # Drop test table
    cur.execute("DROP TABLE IF EXISTS test_databricks")
    conn.commit()
    print("✅ Test table 'test_databricks' dropped")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Cleanup failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Summary

# COMMAND ----------

print("=" * 60)
print("PostgreSQL External TCP Access Test - PASSED")
print("=" * 60)
print(f"Host: {PG_HOST}:{PG_PORT}")
print(f"User: {USER}")
print(f"Connection: ✅ Success")
print(f"Create Table: ✅ Success")
print(f"Insert Data: ✅ Success")
print(f"Query Data: ✅ Success")
print(f"Cleanup: ✅ Success")
print("=" * 60)
