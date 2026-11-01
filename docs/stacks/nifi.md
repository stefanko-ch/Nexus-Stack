---
title: "Apache NiFi"
---

## Apache NiFi

![Apache NiFi](https://img.shields.io/badge/Apache_NiFi-728E9B?logo=apachenifi&logoColor=white)

**Visual data-flow automation — ingest, route, transform and deliver data with full provenance**

NiFi moves data. Processors on a canvas pull from files, HTTP APIs, databases, Kafka and object storage, route and transform each record, and deliver it onward, with back-pressure, retries and a provenance trail for every record. Where [Kestra](kestra.md) and [Airflow](airflow.md) orchestrate jobs, NiFi is the pipe the data flows through.

| Setting | Value |
|---------|-------|
| Default Port | `8445` — `nifi-proxy` (bound to `127.0.0.1`) |
| Suggested Subdomain | `nifi` |
| Entry point | `https://nifi.<domain>/nifi` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Single-user login, generated per deployment — see below |
| Persistence | The flow, under `/mnt/nexus-data/nifi`, backed up to R2 |
| Website | [nifi.apache.org](https://nifi.apache.org) |
| Source | [GitHub](https://github.com/apache/nifi) |

### Two containers, and why

NiFi 2.x serves HTTPS only, with a self-signed certificate it generates for its own host name, and it refuses requests whose `Host` is not on that certificate. The tunnel reaches every origin over plain HTTP, so `nifi-proxy` (nginx) sits in between:

- it takes HTTP from the tunnel and opens TLS to NiFi as `nifi`, the container's hostname, which is what the certificate names;
- it passes the public host name on in `X-ProxyHost` / `X-ProxyScheme` / `X-ProxyPort`, which NiFi uses to build its URLs.

NiFi only accepts an `X-ProxyHost` listed in `NIFI_WEB_PROXY_HOST`, which the deploy sets to the stack's public host name. Checked locally: that host gets the UI, any other gets `421`.

NiFi listens on every interface (`NIFI_WEB_HTTPS_HOST=0.0.0.0`). Its default, the container's host name, resolves to one of its two networks only, and the proxy's connections on the other were refused.

### Login

NiFi's single-user login, set from the environment on every start:

- **Username:** the stack user's email (on a class stack, the student's), else `ADMIN_EMAIL`
- **Password:** generated per deployment, 24 characters

Both are in Infisical, folder `nifi`, as `NIFI_USERNAME` and `NIFI_PASSWORD`. NiFi needs at least 12 characters; with fewer it silently replaces the login with a random one printed only to its log, so the deploy refuses a shorter one.

### Persistence

The flow — `flow.json.gz` and its archive — lives in `/opt/nifi/persist`, bind-mounted from `/mnt/nexus-data/nifi` (owned by `1000:1000`) and backed up to R2 with NiFi stopped.

`conf/` itself is not mounted: the image rewrites files there on every start, and an empty bind mount would hide the ones it ships. Instead, the entrypoint points `nifi.flow.configuration.file` into the mounted directory before handing over to the image's own start script.

Sensitive values inside the flow (passwords, keys) are encrypted with `NIFI_SENSITIVE_PROPS_KEY`. It is generated per deployment and kept across a rebuild teardown, because the restored flow can only be decrypted with the key it was written with.

Not kept: the FlowFile, content and provenance repositories (data in flight and its history) and processor state. A teardown is a clean stop of the pipes, not of what they carry.

### Memory

Heap 512 MB initial, 1 GB maximum; container limit 2 GB. NiFi takes two to three minutes to start.

### Health

The probe calls `https://nifi:8443/nifi-api/access/config` with curl and accepts any HTTP answer — a `401` means the listener is up. It uses `nifi`, not `localhost`, which gets no connection.
