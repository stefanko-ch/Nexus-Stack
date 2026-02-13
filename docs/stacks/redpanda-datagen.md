## Redpanda Datagen

![Redpanda Datagen](https://img.shields.io/badge/Redpanda_Datagen-E4405F?logo=redpanda&logoColor=white)

**Test data generator for Redpanda topics**

A separate stack for generating realistic test data into Redpanda topics. Uses Redpanda Connect with a pre-configured data generation pipeline. Enable this service via the Control Panel when you need test data - disable it when not needed to avoid overhead.

| Setting | Value |
|---------|-------|
| Default Port | `4196` |
| Suggested Subdomain | `redpanda-datagen` |
| Public Access | No (test data generator) |
| Target Topic | `test-events` |
| Message Rate | 1 message/second |

### Generated Data Format

The datagen produces realistic e-commerce event data:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00Z",
  "user_id": 4523,
  "event_type": "purchase",
  "amount": 249,
  "metadata": {
    "browser": "Chrome",
    "country": "DE"
  }
}
```

### Event Types

| Event | Description |
|-------|-------------|
| `click` | User clicked on an element |
| `view` | User viewed a page |
| `purchase` | User made a purchase (includes amount) |
| `signup` | User signed up |

### Usage

1. **Enable** the `redpanda-datagen` service in the Control Panel
2. **View data** in Redpanda Console at the `test-events` topic
3. **Disable** when done testing to stop data generation

> ℹ️ **Note:** Data generation runs continuously while the service is enabled (1 msg/sec). Disable via Control Panel when not needed.
