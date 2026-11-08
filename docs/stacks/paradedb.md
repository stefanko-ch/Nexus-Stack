---
title: "ParadeDB"
---

## ParadeDB

![ParadeDB](https://img.shields.io/badge/ParadeDB-1C1C1C?logo=postgresql&logoColor=white)

**PostgreSQL with full-text search (BM25) and fast analytics**

ParadeDB is PostgreSQL 18 with the `pg_search` extension. A `bm25` index gives relevance-ranked full-text search, fuzzy and phrase matching, highlighting and faceted aggregates, all in SQL. pgvector and PostGIS ship in the same image, so keyword search, vector search and geodata combine in one query.

| Setting | Value |
|---------|-------|
| In-cluster | `paradedb:5432`, database `paradedb` |
| User | `nexus-paradedb` |
| Credentials | Password generated per deployment (Infisical folder `paradedb`) |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `paradedb-data` |
| Website | [paradedb.com](https://www.paradedb.com) |
| Source | [GitHub](https://github.com/paradedb/paradedb) |

### ParadeDB next to OpenSearch and Meilisearch

[OpenSearch](opensearch.md) and [Meilisearch](meilisearch.md) are separate search engines: data is copied in and kept in sync. ParadeDB searches the tables where the data already lives, inside transactions, and every PostgreSQL client in the stack connects unchanged.

### First steps

Connect with any PostgreSQL client on `app-network`, for example [pgAdmin](pgadmin.md), [CloudBeaver](cloudbeaver.md) or a notebook. `pg_search`, `vector` and `postgis` are already created in the `paradedb` database.

```sql
CREATE TABLE products (id serial PRIMARY KEY, description text, category text);
INSERT INTO products (description, category) VALUES
  ('Lightweight running shoes for trail and road', 'Footwear'),
  ('Waterproof hiking boots', 'Footwear'),
  ('Running socks, pack of three', 'Apparel');

CREATE INDEX products_search ON products USING bm25 (id, description, category);

SELECT description, pdb.score(id) AS score
FROM products
WHERE description ||| 'running shoes'
ORDER BY score DESC;
```

`|||` matches any of the terms and `pdb.score` is the BM25 relevance. The first column of the index must be a unique key. See the [ParadeDB docs](https://docs.paradedb.com) for phrase, fuzzy and hybrid queries.

From Python:

```python
import psycopg

conn = psycopg.connect(
    host="paradedb", dbname="paradedb", user="nexus-paradedb",
    password="<PARADEDB_PASSWORD>",
)
```

### Persistence

- **`rebuild` (default): the data does not survive a teardown.** ParadeDB is not in the R2 backup list.
- **`snapshot`: the data survives**, because the whole disk is imaged.

The password takes effect when the volume is first initialised. After that, PostgreSQL keeps the one it was created with, as with the shared `postgres` stack.
