---
title: "Datasette"
---

## Datasette

![Datasette](https://img.shields.io/badge/Datasette-0F3E66?logoColor=white)

**Explore and publish SQLite databases in the browser**

Datasette turns SQLite files into a website:
- every table gets a browsable, filterable view with facets;
- every query gets a shareable URL;
- everything gets a JSON and CSV API.

It is the quickest way to look at a dataset someone hands over, or to give a notebook's results a read-only front end.

| Setting | Value |
|---------|-------|
| Default Port | `8115` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `datasette` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — Datasette has no accounts |
| Persistence | Docker volume `datasette-data` |
| Website | [datasette.io](https://datasette.io) |
| Source | [GitHub](https://github.com/simonw/datasette) |

### Adding a database

Datasette serves every `*.db` file in `/data`, read-only. It reads the directory when it starts, so a new file appears after a restart.

`sqlite-utils` is in the image, so a CSV becomes a table with one command:

```bash
scp cities.csv nexus:/tmp/cities.csv
ssh nexus "docker cp /tmp/cities.csv datasette:/tmp/cities.csv"
ssh nexus "docker exec datasette sqlite-utils insert /data/demo.db cities /tmp/cities.csv --csv"
ssh nexus "docker restart datasette"
```

The table is then at `https://datasette.<domain>/demo/cities`, and as JSON at `/demo/cities.json`.

### Image

The official `datasetteproject/datasette` image is amd64 only. `stacks/datasette/Dockerfile` builds one from `python:3.12-slim` with `datasette==0.65.5` and `sqlite-utils==4.2.1`, so it runs on amd64 and arm64. It runs as an unprivileged `datasette` user (1000).

### Authentication

Datasette has no login, and it serves its databases read-only. Anyone who passes Cloudflare Access can read every database in the volume. Datasette is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`, which keeps it from being made public or given a firewall rule.

### Persistence

The databases live in the `datasette-data` volume.

- **`rebuild` (default): they do not survive a teardown.** Datasette is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
