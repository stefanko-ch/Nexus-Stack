"""Getting Started with PostgREST in Marimo.

PostgREST is a Go binary that introspects a Postgres schema and serves
every table / view / RPC as a REST endpoint. The Nexus-Stack PostgREST
stack points it at the shared `postgres` stack, so any tables you
create in that database are immediately query-able over HTTP.

This notebook walks through the API surface:

    1. One-time setup: create a demo schema with a table + sample rows
       (run once via CloudBeaver/pgAdmin/Adminer/psql — see below)
    2. List rows with GET /<table>
    3. Filter (?col=eq.value), order (?order=col.desc), paginate (Range header)
    4. Insert via POST
    5. Update via PATCH
    6. Delete via DELETE
    7. Fetch the auto-generated OpenAPI spec

Network: hits PostgREST at `http://postgrest:3000` (the internal
app-network hostname). This bypasses Cloudflare Access since we're
already inside the trusted compose network — no JWT needed for the
anon-role traffic in the lab default. For external clients hitting
`https://postgrest.<domain>`, Cloudflare Access at the edge gates
who reaches the API.

No extra pip installs needed. The notebook uses `urllib.request` +
`json` from the stdlib so it works on the un-augmented Marimo image.

This file was seeded into your Gitea workspace repo from
``nexus-stack/examples/workspace-seeds/marimo/Getting_Started_PostgREST.py``.
Edit it in Gitea or directly in Marimo — your changes persist across
spin-ups (seeding only adds new files, never overwrites).
"""

import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Getting Started with PostgREST on Marimo

        PostgREST exposes every table in the configured schema as a REST endpoint.
        We hit the internal hostname `http://postgrest:3000` (no Cloudflare Access
        round-trip from inside the compose network).

        ## One-time setup (run in CloudBeaver / pgAdmin / Adminer / psql)

        Before the cells below work, create a small demo schema in the shared
        Postgres. Open CloudBeaver at `https://cloudbeaver.<domain>` (or
        Adminer / pgAdmin), connect to the shared `postgres` database as
        `nexus-postgres`, and run:

        ```sql
        CREATE TABLE IF NOT EXISTS demo_books (
            id          SERIAL PRIMARY KEY,
            title       TEXT NOT NULL,
            author      TEXT NOT NULL,
            year        INT,
            in_stock    BOOLEAN DEFAULT TRUE
        );

        INSERT INTO demo_books (title, author, year, in_stock) VALUES
            ('The Go Programming Language', 'Donovan & Kernighan', 2015, TRUE),
            ('Designing Data-Intensive Applications', 'Kleppmann', 2017, TRUE),
            ('Database Internals', 'Petrov', 2019, FALSE),
            ('Streaming Systems', 'Akidau et al.', 2018, TRUE),
            ('SQL Performance Explained', 'Winand', 2012, TRUE)
        ON CONFLICT DO NOTHING;
        ```

        Then signal PostgREST to refresh its schema cache (run once on the
        nexus server, or via Portainer's exec console on the postgrest
        container):

        ```bash
        docker exec postgrest kill -SIGUSR1 1
        ```

        Now restart this notebook's cells. The `demo_books` table is live.
        """
    )
    return


@app.cell
def _():
    # Stdlib only — no pip installs needed. Works on the un-augmented
    # Marimo image (which ships duckdb/polars/ibis but not httpx/requests).
    import json
    import urllib.parse
    import urllib.request

    POSTGREST = "http://postgrest:3000"

    def get(path: str, params: dict | None = None, headers: dict | None = None):
        url = f"{POSTGREST}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")

    def post(path: str, body: dict | list, headers: dict | None = None):
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{POSTGREST}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Prefer": "return=representation", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")

    def patch(path: str, body: dict, headers: dict | None = None):
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{POSTGREST}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Prefer": "return=representation", **(headers or {})},
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")

    def delete(path: str, headers: dict | None = None):
        req = urllib.request.Request(f"{POSTGREST}{path}", headers=headers or {}, method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()

    return POSTGREST, delete, get, patch, post, urllib


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. List rows — GET `/demo_books`

        Plain GET returns every row in the configured schema as a JSON array.
        """
    )
    return


@app.cell
def _(get):
    status, _, books = get("/demo_books")
    (status, books)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Filter, order, paginate

        PostgREST gives you SQL-grade query semantics in URL parameters:

        - `?col=eq.value`  → equals
        - `?col=gt.2015`   → greater than
        - `?col=in.(a,b)`  → IN clause
        - `?col=ilike.*Sql*` → case-insensitive LIKE
        - `?order=col.desc` → ORDER BY DESC
        - Range header `0-1` → pagination (window of rows 0-1 inclusive)
        """
    )
    return


@app.cell
def _(get):
    # In-stock books from 2017 or newer, newest first.
    _, _, recent = get(
        "/demo_books",
        params={"in_stock": "is.true", "year": "gte.2017", "order": "year.desc"},
    )
    recent


@app.cell
def _(get):
    # Pagination via the Range header — rows 0..1 (first two).
    _, headers, first_two = get("/demo_books", headers={"Range": "0-1"})
    {"Content-Range": headers.get("Content-Range"), "rows": first_two}


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Insert — POST `/demo_books`

        Send a single object or an array. `Prefer: return=representation` (set
        by the helper above) makes PostgREST echo the inserted row back, which
        is handy when the row picks up server-side defaults (here: `id`).
        """
    )
    return


@app.cell
def _(post):
    _, _, inserted = post(
        "/demo_books",
        body={
            "title": "Fundamentals of Software Architecture",
            "author": "Richards & Ford",
            "year": 2020,
            "in_stock": True,
        },
    )
    inserted


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Update — PATCH `/demo_books?id=eq.N`

        PATCH applies a partial update to whatever rows the filter matches.
        Without a filter PostgREST will refuse (preventing accidental
        full-table updates) — same protection applies to DELETE.
        """
    )
    return


@app.cell
def _(get, patch, urllib):
    # Bring "Database Internals" back in stock. The title contains a space, so
    # the filter has to be URL-encoded — urllib rejects a literal space in the
    # request path with `InvalidURL: URL can't contain control characters`.
    _filter = urllib.parse.urlencode({"title": "eq.Database Internals"})
    _, _, updated = patch(f"/demo_books?{_filter}", body={"in_stock": True})
    _, _, all_books = get("/demo_books", params={"order": "id.asc"})
    {"updated": updated, "all_books": all_books}


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. OpenAPI spec — GET `/`

        PostgREST auto-generates an OpenAPI 2.0 spec at the root. Paste this
        into Hoppscotch / Swagger UI / any OpenAPI viewer for an interactive
        playground over every table and RPC in the schema.
        """
    )
    return


@app.cell
def _(get):
    _, _, spec = get("/")
    # Just show the high-level shape — the full spec gets big once you have
    # more than a few tables.
    {
        "info": spec.get("info"),
        "host": spec.get("host"),
        "paths_count": len(spec.get("paths", {})),
        "sample_paths": list(spec.get("paths", {}).keys())[:5],
    }


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Where to go next

        - **Tighten the anon role.** The shipped default uses the shared-Postgres
          superuser as `PGRST_DB_ANON_ROLE` — fine for a lab, not for multi-user
          deployments. See the [PostgREST stack docs](https://nexus-stack.ch/docs/stacks/postgrest/#production-hardening--replace-the-superuser-anon-role)
          for the SQL recipe to switch to a least-privilege `web_anon` role.
          (This link points at the published Nexus-Stack docs site, not the
          workspace repo — the seeded notebook lives in your Gitea workspace
          but the `docs/` tree only exists in the upstream Nexus-Stack repo.)
        - **Mint JWTs for write paths.** Once you have separate roles, elevate
          past anon by sending `Authorization: Bearer <token>` where the JWT's
          `role` claim names the Postgres role to switch to. The secret is in
          Infisical at `/postgrest/POSTGREST_JWT_SECRET`.
        - **Stored functions as endpoints.** Any Postgres function (RPC) is
          callable at `POST /rpc/<name>` — useful for batched inserts,
          server-side computation, or anything you don't want to express as
          a table operation.
        - **Embed related rows.** `?select=*,fk_table(*)` follows foreign-key
          relationships and embeds the related rows inline — a single round-trip
          for joined data. The PostgREST docs have the full grammar.
        """
    )
    return


if __name__ == "__main__":
    app.run()
