---
title: "CyberChef"
---

## CyberChef

![CyberChef](https://img.shields.io/badge/CyberChef-1B365D?logo=gchq&logoColor=white)

**The Cyber Swiss Army Knife — drag-and-drop data manipulation**

CyberChef is a web-based tool from [GCHQ](https://www.gchq.gov.uk/) (UK Government Communications Headquarters) that chains ~400 "operations" into a "recipe" you build by drag-and-drop. Useful for:
- Decode/encode (Base64, URL, hex, JWT, ASCII85, …)
- Hashing (MD5, SHA-x, BLAKE, HMAC, bcrypt, …)
- Crypto (AES/DES/RSA, JWT verify, X.509 parse, …)
- Compression (Gzip, Bzip2, Zip, …)
- Format conversion (JSON ↔ YAML, CSV, XML, …)
- Regex extract/replace, language detect, magic auto-decode
- Live demos in class: "From Base64 → Gunzip → Pretty-print JSON" on a log payload in three drag-drops

> **The container only serves the static HTML/JS/CSS bundle** (~30 MB image, ~10 MB RAM idle) — it has no application-level logic that processes or stores user input. CyberChef operations execute client-side in the browser. Note: a small number of operations (e.g. "DNS over HTTPS", "HTTP request", "URL fetch") deliberately call external services; if you avoid those, recipe inputs stay within the browser process. Standard browser-level caveats still apply (extensions, dev tools, page sources).

| Setting | Value |
|---------|-------|
| Default Port | `8400` |
| Suggested Subdomain | `cyberchef` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [gchq.github.io/CyberChef](https://gchq.github.io/CyberChef/) |
| Source | [GitHub](https://github.com/gchq/CyberChef) |
| Docker image | [`mpepping/cyberchef`](https://hub.docker.com/r/mpepping/cyberchef) (community-maintained mirror — tracks upstream GCHQ releases) |

### Usage

1. Enable the **CyberChef** service in the Control Plane → Spin Up
2. Visit `https://cyberchef.YOUR_DOMAIN`, authenticate via Cloudflare Access OTP
3. Drag operations from the left panel into the recipe column, paste input into the bottom-left
4. Output renders live as you tweak the recipe

### Image pinning

Pinned to `mpepping/cyberchef:v10.24.0` (current upstream GCHQ/CyberChef release). The `mpepping/cyberchef` image is a community-maintained Docker wrapper around upstream — there is no official GCHQ-published image. Bump the `IMAGE_CYBERCHEF` env var (or `services.yaml`) when a newer upstream release adds operations relevant to your classroom.
