---
title: "Label Studio"
---

## Label Studio

![Label Studio](https://img.shields.io/badge/Label_Studio-FF7557?logo=labelstudio&logoColor=white)

**Data labelling for text, images, audio and tables**

Label Studio is an open-source annotation tool. A project defines a labelling interface — classification, named entities, bounding boxes, segmentation, transcription, ranking — and tasks are imported, labelled in the browser and exported in the formats training code expects (JSON, CSV, COCO, YOLO, spaCy and more). It covers the step before model training that nothing else in the stack does.

| Setting | Value |
|---------|-------|
| Default Port | `8280` on the host (bound to `127.0.0.1`), `8080` in the container |
| Suggested Subdomain | `label-studio` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Account and API token, generated per deployment — see below |
| Persistence | `/mnt/nexus-data/label-studio`, backed up to R2 |
| Website | [labelstud.io](https://labelstud.io) |
| Source | [GitHub](https://github.com/HumanSignal/label-studio) |

### Login

Cloudflare Access is the outer gate. Label Studio then asks for its own account, created on first start:

- **Email:** the stack user's email (on a class stack, the student's), else `ADMIN_EMAIL`
- **Password:** generated per deployment
- **API token:** generated per deployment, for the SDK and the REST API

All three are in Infisical, folder `label-studio`: `LABEL_STUDIO_USERNAME`, `LABEL_STUDIO_PASSWORD`, `LABEL_STUDIO_API_TOKEN`. Sign-up without an invitation link is disabled.

Label Studio creates the account only if it does not exist yet, so the password belongs to the data directory it was first started with.

The API token is what Label Studio calls a *legacy* token, and 1.23 rejects those unless `LABEL_STUDIO_ENABLE_LEGACY_API_TOKEN=true`, which the compose file sets. The newer personal access tokens can only be created in the UI, so this is the one that works without a UI visit.

### From a notebook

```python
from label_studio_sdk import LabelStudio

ls = LabelStudio(base_url="http://label-studio:8080", api_key="<LABEL_STUDIO_API_TOKEN>")
```

Inside the cluster, use `http://label-studio:8080`, not the public hostname, which is behind Cloudflare Access.

### Behind the tunnel

Django compares a login's `Origin` with `CSRF_TRUSTED_ORIGINS`. The deploy sets it, and `LABEL_STUDIO_HOST`, to the stack's public `https://` URL; without it every login through Cloudflare is refused with a CSRF 403. The session and CSRF cookies are marked secure.

### Persistence

The SQLite database, uploaded media and the generated Django secret key live in `/label-studio/data`, bind-mounted from `/mnt/nexus-data/label-studio` and owned by the image's user (`1001:0`). The rebuild teardown stops Label Studio and copies the directory to R2; the next spin-up restores it.

Importing tasks from URLs that point at other containers is blocked by Label Studio's SSRF protection, which stays on. Upload files through the UI or the API instead.

### Telemetry

`LABEL_STUDIO_COLLECT_ANALYTICS=false`, and both Sentry DSNs, which default to Label Studio's own, are set empty.

### Health

`GET /health` answers `{"status":"UP"}` (curl, inside the container).
