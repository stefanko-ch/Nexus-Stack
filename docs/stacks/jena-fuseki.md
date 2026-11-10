---
title: "Apache Jena Fuseki"
---

## Apache Jena Fuseki

![Jena Fuseki](https://img.shields.io/badge/Apache_Jena_Fuseki-D22128?logo=apache&logoColor=white)

**RDF triple store with a SPARQL endpoint**

Fuseki stores RDF triples and answers SPARQL 1.1 queries and updates, with named graphs, the graph store protocol and SHACL validation.

| Setting | Value |
|---------|-------|
| Default Port | `3030` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `jena-fuseki` |
| Public Access | No (protected by Cloudflare Access) |
| In-cluster | `http://jena-fuseki:3030` |
| Credentials | `nexus-admin`, password generated per deployment (Infisical folder `jena-fuseki`), HTTP Basic auth |
| Persistence | Docker volumes `jena-fuseki-databases` and `jena-fuseki-configuration` |
| Website | [jena.apache.org](https://jena.apache.org/documentation/fuseki2/) |

### Where it fits

[Neo4j](neo4j.md) and [Memgraph](memgraph.md) are property-graph databases with Cypher. Fuseki is the semantic-web side: RDF, SPARQL, ontologies and linked data. A [Zeppelin](zeppelin.md) notebook can query it from a `%python` paragraph:

```python
%python
import requests

r = requests.post("http://jena-fuseki:3030/ds/sparql",
                  auth=("{fuseki.user}", "{fuseki.password}"),
                  data={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10"},
                  headers={"Accept": "application/sparql-results+json"})
r.json()["results"]["bindings"]
```

The `{fuseki.user}` and `{fuseki.password}` placeholders keep the password out of the notebook, which Zeppelin saves together with its revision history. They use Zeppelin's [credential injection](https://zeppelin.apache.org/docs/0.12.1/usage/interpreter/overview.html#credential-injection):

1. Under **Credential** (user menu), add an entry with the entity `fuseki`, the username `nexus-admin` and `JENA_FUSEKI_PASSWORD` from Infisical.
2. Under **Interpreter → python**, add the property `injectCredentials` with the value `true`, and restart the interpreter.

Zeppelin then replaces the placeholders when the paragraph runs, and removes the injected password from the paragraph's output. On a server, the query above returned `200` this way. Without the injection Fuseki answers `401`. The removal from the output was not checked.

The interpreter property is stored in Zeppelin's `conf/`, which is not on a volume: after the container is recreated, add `injectCredentials` again. The credential entry has the same limit.

If a password has already been typed into a paragraph, deleting it does not remove it from older revisions. Rotate it instead.

Zeppelin's own `%sparql` interpreter does not work here: it has no setting for credentials, and every Fuseki dataset requires a login. Do not put the password into its endpoint URL either, because the interpreter logs that URL.

### Image

Apache Jena publishes no Docker image of its own. This stack uses [secoresearch/fuseki](https://hub.docker.com/r/secoresearch/fuseki), a maintained build that follows Jena's releases.

It comes with a dataset `ds`, which uses TDB with a Lucene text index. Its default graph is the union of the named graphs. The stack turns on SPARQL Update, the read-write graph store and SHACL for `ds`. More datasets, in TDB2, are created in the UI under **manage**.

### Authentication

Everything except `/$/ping` and `/$/status` needs a login, the UI included: the browser asks for it.

The image's own configuration protects only the admin API. It leaves every dataset readable, and with updates on, writable by anyone on `app-network`. So the stack writes its own `shiro.ini` on every start.

### First steps

```bash
curl -u nexus-admin:<JENA_FUSEKI_PASSWORD> http://jena-fuseki:3030/ds/update \
  --data-urlencode 'update=INSERT DATA { GRAPH <urn:demo> {
    <urn:alice> <http://xmlns.com/foaf/0.1/knows> <urn:bob> } }'

curl -u nexus-admin:<JENA_FUSEKI_PASSWORD> http://jena-fuseki:3030/ds/sparql \
  --data-urlencode 'query=SELECT ?s ?o WHERE { ?s <http://xmlns.com/foaf/0.1/knows> ?o }'
```

Data in the default graph of `ds` is not part of that union. Address it as `GRAPH <urn:x-arq:DefaultGraph>`.

### Persistence

Datasets are in `jena-fuseki-databases`. Datasets created in the UI also have a configuration file, which is in `jena-fuseki-configuration`.

- **`rebuild` (default): they do not survive a teardown.** Fuseki is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
