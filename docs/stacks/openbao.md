---
title: "OpenBao"
---

## OpenBao

![OpenBao](https://img.shields.io/badge/OpenBao-1F2937?logo=vault&logoColor=white)

**Secrets management, the open-source fork of HashiCorp Vault**

OpenBao stores secrets with versions, issues short-lived credentials, encrypts data as a service and controls all of it with policies and tokens. It has a web UI, a CLI (`bao`, compatible with `vault`) and an HTTP API.

| Setting | Value |
|---------|-------|
| Default Port | `8126` (bound to `127.0.0.1` on the host; container port 8200) |
| Suggested Subdomain | `openbao` |
| Public Access | No (protected by Cloudflare Access) |
| In-cluster | `http://openbao:8200` |
| Credentials | `nexus-admin` (method **Username**), password generated per deployment (Infisical folder `openbao`) |
| Persistence | Docker volume `openbao-data` |
| Website | [openbao.org](https://openbao.org) |

### OpenBao and Infisical

[Infisical](infisical.md) is the stack's own secret store: the deploy writes every generated password there. OpenBao is not wired into the deploy. It is a workspace for learning how production systems handle secrets: policies, token TTLs, dynamic database users, transit encryption.

### How it starts

OpenBao does not run in dev mode here. Storage is persistent (Raft, one node), so secrets survive a restart.

A vault normally starts *sealed* and waits for unseal keys. This stack uses a **static seal**: a 32-byte key generated per deployment (`OPENBAO_UNSEAL_KEY` in Infisical) unseals it on every start.

On the first start, `openbao-init`:

1. initialises the server,
2. enables the **userpass** auth method and creates `nexus-admin` with a policy that allows everything,
3. mounts a KV v2 engine at `secret/`,
4. revokes the root token.

The recovery key from the init is discarded, so `nexus-admin` is the way in. Do not delete that user or its policy.

### First steps

In the UI choose the **Username** method and sign in. Or from a notebook on `app-network` (`pip install hvac`):

```python
import hvac

client = hvac.Client(url="http://openbao:8200")
client.auth.userpass.login(username="nexus-admin", password="<OPENBAO_PASSWORD>")

client.secrets.kv.v2.create_or_update_secret(path="demo", secret={"api_key": "abc"})
print(client.secrets.kv.v2.read_secret_version(path="demo")["data"]["data"])
```

The login, a KV write and a read were tested over the HTTP API. The `hvac` snippet was not run here.

Next steps worth trying:

- `bao secrets enable transit` for encryption as a service.
- `bao secrets enable database` with the [Postgres](postgres.md) stack, for dynamic database users.
- A narrower policy and a second user.

### Security notes

- Whoever holds both `OPENBAO_UNSEAL_KEY` and the volume can decrypt everything in OpenBao. That is the trade-off of auto-unseal without a cloud KMS.
- The admin password is passed to `bao` on stdin, never on a command line.
- The init script revokes the token it logs in with to check the password.

### Persistence

Secrets, policies and users are in `openbao-data`.

- **`rebuild` (default): they do not survive a teardown.** A rebuild also generates a new seal key and admin password. OpenBao is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged. The seal key and password stay the same.
