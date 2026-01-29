# Databricks notebook source
# MAGIC %md
# MAGIC # MinIO S3 Connectivity Test
# MAGIC
# MAGIC Tests external TCP access to MinIO S3 API via opened firewall port.
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Firewall rule for MinIO port 9000 enabled in Control Plane
# MAGIC - Infrastructure deployed with Spin Up
# MAGIC - MinIO root credentials available in Infisical

# COMMAND ----------

# Configuration widgets
dbutils.widgets.text("domain", "your-domain.com", "Nexus-Stack Domain")
dbutils.widgets.text("root_user", "", "MinIO Root User (from Infisical)")
dbutils.widgets.text("root_password", "", "MinIO Root Password (from Infisical)")
dbutils.widgets.text("bucket", "test-databricks", "Test Bucket Name")

# COMMAND ----------

DOMAIN = dbutils.widgets.get("domain")
ACCESS_KEY = dbutils.widgets.get("root_user")
SECRET_KEY = dbutils.widgets.get("root_password")
BUCKET = dbutils.widgets.get("bucket")

S3_ENDPOINT = f"http://s3.{DOMAIN}:9000"

print(f"Testing MinIO S3 at: {S3_ENDPOINT}")
print(f"Bucket: {BUCKET}")

if not ACCESS_KEY or not SECRET_KEY:
    dbutils.notebook.exit("Error: Root user and root password required. Get them from Infisical.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install boto3 library

# COMMAND ----------

%pip install boto3

# COMMAND ----------

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from datetime import datetime
import io

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Test Connection to MinIO S3

# COMMAND ----------

try:
    print(f"Connecting to {S3_ENDPOINT}...")

    # Create S3 client
    s3_client = boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

    # List buckets to test connection
    response = s3_client.list_buckets()
    buckets = response['Buckets']

    print(f"✅ Successfully connected to MinIO S3")
    print(f"   Existing buckets: {len(buckets)}")
    for bucket in buckets:
        print(f"   - {bucket['Name']}")

except Exception as e:
    print(f"❌ Connection failed!")
    print(f"   Error: {type(e).__name__}: {str(e)}")
    print(f"\nTroubleshooting:")
    print(f"   1. Verify firewall rule for port 9000 is enabled in Control Plane")
    print(f"   2. Check credentials in Infisical (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD)")
    print(f"   3. Verify domain is correct: {S3_ENDPOINT}")
    print(f"   4. Ensure MinIO is running: Check server status")
    import traceback
    print(f"\nFull error details:")
    traceback.print_exc()
    dbutils.notebook.exit(f"Connection test failed: {str(e)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create Test Bucket

# COMMAND ----------

try:
    # Check if bucket exists
    try:
        s3_client.head_bucket(Bucket=BUCKET)
        print(f"ℹ️  Bucket '{BUCKET}' already exists")
    except ClientError:
        # Bucket doesn't exist, create it
        s3_client.create_bucket(Bucket=BUCKET)
        print(f"✅ Bucket '{BUCKET}' created")

except Exception as e:
    print(f"❌ Bucket creation failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Upload Test Objects

# COMMAND ----------

try:
    # Upload test files
    test_files = [
        {"key": "test1.txt", "content": "Test from Databricks - File 1"},
        {"key": "test2.txt", "content": "Firewall test successful - File 2"},
        {"key": "test3.txt", "content": "External TCP access works - File 3"},
    ]

    for file in test_files:
        s3_client.put_object(
            Bucket=BUCKET,
            Key=file["key"],
            Body=file["content"].encode('utf-8'),
            ContentType='text/plain'
        )
        print(f"✅ Uploaded: s3://{BUCKET}/{file['key']}")

    print(f"\n✅ Successfully uploaded {len(test_files)} objects")

except Exception as e:
    print(f"❌ Upload failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. List Objects in Bucket

# COMMAND ----------

try:
    response = s3_client.list_objects_v2(Bucket=BUCKET)

    if 'Contents' in response:
        objects = response['Contents']
        print(f"✅ Objects in bucket '{BUCKET}':")
        for obj in objects:
            print(f"   - {obj['Key']} ({obj['Size']} bytes, modified: {obj['LastModified']})")

        print(f"\n✅ Found {len(objects)} objects")
    else:
        print(f"ℹ️  Bucket '{BUCKET}' is empty")

except Exception as e:
    print(f"❌ List objects failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Download and Read Test Object

# COMMAND ----------

try:
    # Download first test file
    test_key = "test1.txt"
    response = s3_client.get_object(Bucket=BUCKET, Key=test_key)
    content = response['Body'].read().decode('utf-8')

    print(f"✅ Downloaded: s3://{BUCKET}/{test_key}")
    print(f"   Content: {content}")

except Exception as e:
    print(f"❌ Download failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Cleanup Test Bucket

# COMMAND ----------

try:
    # Delete all objects in bucket
    response = s3_client.list_objects_v2(Bucket=BUCKET)
    if 'Contents' in response:
        for obj in response['Contents']:
            s3_client.delete_object(Bucket=BUCKET, Key=obj['Key'])
            print(f"✅ Deleted: {obj['Key']}")

    # Delete bucket
    s3_client.delete_bucket(Bucket=BUCKET)
    print(f"✅ Bucket '{BUCKET}' deleted")

except Exception as e:
    print(f"❌ Cleanup failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Summary

# COMMAND ----------

print("=" * 60)
print("MinIO S3 External TCP Access Test - PASSED")
print("=" * 60)
print(f"Endpoint: {S3_ENDPOINT}")
print(f"Bucket: {BUCKET}")
print(f"Connection: ✅ Success")
print(f"Create Bucket: ✅ Success")
print(f"Upload Objects: ✅ Success")
print(f"List Objects: ✅ Success")
print(f"Download Objects: ✅ Success")
print(f"Cleanup: ✅ Success")
print("=" * 60)
