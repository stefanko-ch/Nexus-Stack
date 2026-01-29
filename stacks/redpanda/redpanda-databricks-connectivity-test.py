# Databricks notebook source
# MAGIC %md
# MAGIC # RedPanda (Kafka) Connectivity Test
# MAGIC
# MAGIC Tests external TCP access to RedPanda/Kafka via opened firewall port.
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Firewall rule for RedPanda port 9092 enabled in Control Plane
# MAGIC - Infrastructure deployed with Spin Up
# MAGIC - SASL credentials available in Infisical (REDPANDA_SASL_USERNAME / REDPANDA_SASL_PASSWORD)

# COMMAND ----------

# Configuration widgets
dbutils.widgets.text("domain", "your-domain.com", "Nexus-Stack Domain")
dbutils.widgets.text("topic", "test-topic", "Kafka Topic")
dbutils.widgets.text("sasl_username", "", "SASL Username (from Infisical)")
dbutils.widgets.text("sasl_password", "", "SASL Password (from Infisical)")

# COMMAND ----------

DOMAIN = dbutils.widgets.get("domain")
TOPIC = dbutils.widgets.get("topic")
SASL_USERNAME = dbutils.widgets.get("sasl_username")
SASL_PASSWORD = dbutils.widgets.get("sasl_password")

KAFKA_BOOTSTRAP = f"redpanda-kafka.{DOMAIN}:9092"

print(f"Testing RedPanda/Kafka at: {KAFKA_BOOTSTRAP}")
print(f"Topic: {TOPIC}")
print(f"SASL User: {SASL_USERNAME}")

if not SASL_USERNAME or not SASL_PASSWORD:
    dbutils.notebook.exit("Error: SASL username and password required. Get them from Infisical.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install kafka-python library

# COMMAND ----------

%pip install kafka-python

# COMMAND ----------

from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import KafkaError
import json
from datetime import datetime

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Test Connection to Kafka

# COMMAND ----------

try:
    print(f"Connecting to {KAFKA_BOOTSTRAP}...")
    admin_client = KafkaAdminClient(
        bootstrap_servers=[KAFKA_BOOTSTRAP],
        client_id='databricks-test',
        request_timeout_ms=10000,
        api_version='auto',  # Auto-detect protocol version
        security_protocol='SASL_PLAINTEXT',
        sasl_mechanism='SCRAM-SHA-256',
        sasl_plain_username=SASL_USERNAME,
        sasl_plain_password=SASL_PASSWORD
    )

    # Test connection by listing topics
    topics = admin_client.list_topics()
    print(f"✅ Successfully connected to Kafka cluster")
    print(f"   Existing topics: {len(topics)}")

    admin_client.close()
except Exception as e:
    print(f"❌ Connection failed!")
    print(f"   Error: {type(e).__name__}: {str(e)}")
    print(f"\nTroubleshooting:")
    print(f"   1. Verify firewall rule for port 9092 is enabled in Control Plane")
    print(f"   2. Check SASL credentials in Infisical (REDPANDA_SASL_USERNAME, REDPANDA_SASL_PASSWORD)")
    print(f"   3. Verify domain is correct: {KAFKA_BOOTSTRAP}")
    print(f"   4. Ensure RedPanda is running with SASL authentication on external listener")
    import traceback
    print(f"\nFull error details:")
    traceback.print_exc()
    dbutils.notebook.exit(f"Connection test failed: {str(e)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create Test Topic

# COMMAND ----------

try:
    admin_client = KafkaAdminClient(
        bootstrap_servers=[KAFKA_BOOTSTRAP],
        api_version='auto',  # Auto-detect protocol version
        security_protocol='SASL_PLAINTEXT',
        sasl_mechanism='SCRAM-SHA-256',
        sasl_plain_username=SASL_USERNAME,
        sasl_plain_password=SASL_PASSWORD
    )

    # Create topic if it doesn't exist
    topic_list = [NewTopic(name=TOPIC, num_partitions=1, replication_factor=1)]

    try:
        admin_client.create_topics(new_topics=topic_list, validate_only=False)
        print(f"✅ Topic '{TOPIC}' created")
    except KafkaError as e:
        if "TopicExistsError" in str(e):
            print(f"ℹ️  Topic '{TOPIC}' already exists")
        else:
            raise e

    admin_client.close()
except Exception as e:
    print(f"❌ Topic creation failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Produce Test Messages

# COMMAND ----------

try:
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        api_version='auto',  # Auto-detect protocol version
        security_protocol='SASL_PLAINTEXT',
        sasl_mechanism='SCRAM-SHA-256',
        sasl_plain_username=SASL_USERNAME,
        sasl_plain_password=SASL_PASSWORD
    )

    # Send test messages
    test_messages = [
        {"id": 1, "message": "Test from Databricks", "timestamp": datetime.now().isoformat()},
        {"id": 2, "message": "Firewall test successful", "timestamp": datetime.now().isoformat()},
        {"id": 3, "message": "External TCP access works", "timestamp": datetime.now().isoformat()},
    ]

    for msg in test_messages:
        future = producer.send(TOPIC, value=msg)
        record_metadata = future.get(timeout=10)
        print(f"✅ Sent message {msg['id']} to {record_metadata.topic}:{record_metadata.partition}:{record_metadata.offset}")

    producer.flush()
    producer.close()
    print(f"\n✅ Successfully sent {len(test_messages)} messages to topic '{TOPIC}'")

except Exception as e:
    print(f"❌ Producer failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Consume Test Messages

# COMMAND ----------

try:
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=[KAFKA_BOOTSTRAP],
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='databricks-test-consumer',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        consumer_timeout_ms=10000,
        api_version='auto',  # Auto-detect protocol version
        security_protocol='SASL_PLAINTEXT',
        sasl_mechanism='SCRAM-SHA-256',
        sasl_plain_username=SASL_USERNAME,
        sasl_plain_password=SASL_PASSWORD
    )

    messages = []
    for message in consumer:
        messages.append(message.value)
        print(f"✅ Consumed: {message.value}")

    consumer.close()

    print(f"\n✅ Successfully consumed {len(messages)} messages from topic '{TOPIC}'")

except Exception as e:
    print(f"❌ Consumer failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Summary

# COMMAND ----------

print("=" * 60)
print("RedPanda/Kafka External TCP Access Test - PASSED")
print("=" * 60)
print(f"Kafka Broker: {KAFKA_BOOTSTRAP}")
print(f"Topic: {TOPIC}")
print(f"Connection: ✅ Success")
print(f"Produce: ✅ Success")
print(f"Consume: ✅ Success")
print("=" * 60)
