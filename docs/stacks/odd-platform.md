---
title: "ODD Platform"
---

## ODD Platform

![ODD Platform](https://img.shields.io/badge/ODD_Platform-2563EB?logoColor=white)

**Open Data Discovery: a catalog with data-quality results**

The Open Data Discovery (ODD) Platform is a catalog built on the [ODD specification](https://github.com/opendatadiscovery/opendatadiscovery-specification). Collectors push metadata from databases, warehouses, BI tools and pipelines. The platform shows each dataset with:
- its lineage;
- owners, terms and tags;
- the results of data-quality tests from Great Expectations, dbt or Soda, next to the dataset they test.

Next to [Marmot](marmot.md) and [OpenMetadata](openmetadata.md), its focus is the quality results inside the catalog.

| Setting | Value |
|---------|-------|
| URL | `https://odd-platform.<domain>` |
| In-cluster | `http://odd-platform:8080` (ingestion API for collectors) |
| Login | `nexus-admin` |
| Credentials | Password generated per deployment (Infisical folder `odd-platform`) |
| Persistence | Docker volume `odd-platform-db-data` |
| Licence | Apache-2.0 |
| Website | [opendatadiscovery.org](https://opendatadiscovery.org) |

### First steps

1. Open `https://odd-platform.<domain>` and log in as `nexus-admin` with `ODD_PLATFORM_PASSWORD` from Infisical.
2. Under **Management → Collectors**, create a collector. ODD shows its token once; copy it.
3. Run a collector against a source with that token. For the [Postgres](postgres.md) stack, the generic collector is a container on `app-network`:

```yaml
# collector_config.yaml
default_pulling_interval: 10
token: "<collector token>"
platform_host_url: "http://odd-platform:8080"
plugins:
  - type: postgresql
    name: nexus_postgres
    host: postgres
    port: 5432
    database: postgres
    user: nexus-postgres
    password: "<POSTGRES_PASSWORD>"
```

The collector images are `ghcr.io/opendatadiscovery/odd-collector`. Running one was not tried here.

Tested:
- `nexus-admin` logged in and could use the API;
- the image's demo accounts `admin`/`admin` and `root`/`root` were refused;
- anonymous requests were redirected to the login;
- a data source created through the API was kept across a restart.

### Login

The image defaults to no authentication at all. The stack switches on the login form with exactly one account, `nexus-admin`, set through `AUTH_LOGIN_FORM_CREDENTIALS`. That replaces the image's demo accounts instead of adding to them. **In ODD every login-form user is an administrator.** OAuth2 and LDAP are also supported if more users with roles are needed.

### Resources

The platform used about 600 MB and its PostgreSQL about 80 MB. The container limit is 1.5 GB.

### Persistence

The catalog is in ODD's PostgreSQL (`odd-platform-db-data`).

- **`rebuild` (default): it does not survive a teardown.** ODD is not in the R2 backup list. Collectors can rebuild the metadata from the sources.
- **`snapshot`: it survives**, because the whole disk is imaged.
