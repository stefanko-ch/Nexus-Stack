## Quickwit

![Quickwit](https://img.shields.io/badge/Quickwit-FF6B6B?logo=quickwit&logoColor=white)

**Cloud-native search engine for log management and analytics**

Quickwit is a search engine designed for log management and analytics, built on top of object storage. It provides sub-second search on log data with minimal infrastructure overhead.

| Setting | Value |
|---------|-------|
| Default Port | `8092` (mapped from internal `7280`) |
| Suggested Subdomain | `quickwit` |
| Public Access | No (Cloudflare Access) |
| Website | [quickwit.io](https://quickwit.io) |
| Source | [GitHub](https://github.com/quickwit-oss/quickwit) |

### Usage

1. Access at `https://quickwit.<domain>`
2. No application-level authentication (relies on Cloudflare Access)
3. Use the web UI to create indexes, ingest data, and run searches

### Data Persistence

Quickwit stores index data in the `quickwit-data` Docker volume, which is mounted to the Hetzner persistent volume. Data persists across teardown/spin-up cycles.
