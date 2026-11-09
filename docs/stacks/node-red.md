---
title: "Node-RED"
---

## Node-RED

![Node-RED](https://img.shields.io/badge/Node--RED-8F0000?logo=nodered&logoColor=white)

**Flow-based low-code programming for IoT and integrations**

Node-RED wires nodes together in the browser: an MQTT input, a function in JavaScript, a Kafka or database output. Flows are deployed with one click and run on the server.

| Setting | Value |
|---------|-------|
| Default Port | `1880` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `node-red` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | `nexus-admin`, password generated per deployment (Infisical folder `node-red`) |
| Persistence | Docker volume `node-red-data` |
| Website | [nodered.org](https://nodered.org) |

### Authentication

The editor runs arbitrary code, so it has a login: `nexus-admin` with `NODE_RED_PASSWORD` from Infisical. The stack's `settings.js` turns on `adminAuth` and hashes the password at start, and Node-RED refuses to start without one. The editor API answers `401` without a token.

HTTP endpoints that a flow creates with an *http in* node are not covered by that login. They are reachable from `app-network` and through the tunnel behind Cloudflare Access.

Usage diagnostics and the update check against nodered.org are switched off.

### First steps

1. Log in, drag an **mqtt in** node onto the canvas and add a broker: server `mosquitto`, port `1883`, and the [Mosquitto](mosquitto.md) credentials under **Security**.
2. Connect it to a **debug** node and press **Deploy**.
3. Messages published to the topic appear in the debug sidebar.

Credentials entered in nodes are stored encrypted in `flows_cred.json`, with a key generated per deployment.

### Persistence

Flows, credentials and nodes installed from the palette are in `node-red-data`.

- **`rebuild` (default): they do not survive a teardown.** Node-RED is not in the R2 backup list. Export flows (**Menu → Export**) to keep them.
- **`snapshot`: they survive**, because the whole disk is imaged.
