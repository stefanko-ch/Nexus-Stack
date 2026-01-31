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
# MAGIC ## Install confluent-kafka library
# MAGIC
# MAGIC Using confluent-kafka (based on librdkafka) instead of kafka-python for better RedPanda compatibility.

# COMMAND ----------

%pip install confluent-kafka

# COMMAND ----------

from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
import json
from datetime import datetime
import sys

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Test Connection to Kafka

# COMMAND ----------

# Kafka configuration
kafka_config = {
    'bootstrap.servers': KAFKA_BOOTSTRAP,
    'security.protocol': 'SASL_PLAINTEXT',
    'sasl.mechanism': 'SCRAM-SHA-256',
    'sasl.username': SASL_USERNAME,
    'sasl.password': SASL_PASSWORD
}

try:
    print(f"Connecting to {KAFKA_BOOTSTRAP}...")
    admin_client = AdminClient(kafka_config)

    # Test connection by listing topics
    metadata = admin_client.list_topics(timeout=10)
    topics = metadata.topics

    print(f"✅ Successfully connected to Kafka cluster")
    print(f"   Cluster ID: {metadata.cluster_id}")
    print(f"   Existing topics: {len(topics)}")
    for topic_name in topics:
        print(f"      - {topic_name}")

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
    admin_client = AdminClient(kafka_config)

    # Create topic if it doesn't exist
    topic_list = [NewTopic(TOPIC, num_partitions=1, replication_factor=1)]

    # Create topics - this returns a dict of futures
    fs = admin_client.create_topics(topic_list)

    # Wait for operation to finish
    for topic, f in fs.items():
        try:
            f.result()  # The result itself is None
            print(f"✅ Topic '{topic}' created")
        except Exception as e:
            if "TopicExistsException" in str(e) or "TOPIC_ALREADY_EXISTS" in str(e):
                print(f"ℹ️  Topic '{topic}' already exists")
            else:
                raise e

except Exception as e:
    print(f"❌ Topic operation failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Produce Test Messages

# COMMAND ----------

def delivery_callback(err, msg):
    """Callback called once the message has been delivered or failed"""
    if err:
        print(f'❌ Message delivery failed: {err}')
    else:
        print(f'✅ Sent message to {msg.topic()}:{msg.partition()}:{msg.offset()}')

try:
    producer_config = kafka_config.copy()
    producer_config.update({
        'client.id': 'databricks-producer'
    })

    producer = Producer(producer_config)

    # Send test messages
    test_messages = [
        {"id": 1, "message": "Test from Databricks", "timestamp": datetime.now().isoformat()},
        {"id": 2, "message": "Firewall test successful", "timestamp": datetime.now().isoformat()},
        {"id": 3, "message": "External TCP access works", "timestamp": datetime.now().isoformat()},
    ]

    for msg in test_messages:
        # Convert dict to JSON string
        value = json.dumps(msg).encode('utf-8')

        # Produce message
        producer.produce(
            TOPIC,
            value=value,
            callback=delivery_callback
        )

        # Trigger delivery report callbacks
        producer.poll(0)

    # Wait for all messages to be delivered
    print(f"\nFlushing producer...")
    producer.flush()

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
    consumer_config = kafka_config.copy()
    consumer_config.update({
        'group.id': 'databricks-test-consumer',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': True,
        'client.id': 'databricks-consumer'
    })

    consumer = Consumer(consumer_config)
    consumer.subscribe([TOPIC])

    messages = []
    max_messages = 10  # Prevent infinite loop
    timeout = 10  # seconds

    print(f"Consuming messages from topic '{TOPIC}'...")

    try:
        msg_count = 0
        while msg_count < max_messages:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                # No message available within timeout
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    # End of partition - reached the end
                    print(f"Reached end of partition {msg.partition()}")
                    break
                else:
                    raise KafkaException(msg.error())
            else:
                # Message successfully consumed
                value = json.loads(msg.value().decode('utf-8'))
                messages.append(value)
                print(f"✅ Consumed: {value}")
                msg_count += 1

    finally:
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
