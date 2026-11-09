---
title: "ZenML"
---

## ZenML

![ZenML](https://img.shields.io/badge/ZenML-431D93?logoColor=white)

**MLOps framework: pipelines, artifacts and model versions**

ZenML records Python pipelines. For every run it keeps each step's inputs and outputs with their lineage, and it tracks model versions with their metrics. The server holds that record and shows it in its dashboard. Pipelines run wherever the ZenML client runs, such as a notebook or [code-server](code-server.md), and connect to the server. ZenML can use the [MLflow](mlflow.md) stack as its experiment tracker.

| Setting | Value |
|---------|-------|
| URL | `https://zenml.<domain>` (dashboard) |
| In-cluster | `http://zenml:8080` |
| Login | `nexus-admin` |
| Credentials | Password generated per deployment (Infisical folder `zenml`) |
| Persistence | Docker volume `zenml-data` (SQLite) |
| Image | `nexus-zenml:0.98.0`, built here from the PyPI release |
| Licence | Apache-2.0 |
| Website | [zenml.io](https://www.zenml.io) |

### First steps

In a notebook or code-server terminal, install the client at the server's version and connect:

```bash
pip install "zenml==0.98.0"
export ZENML_STORE_URL=http://zenml:8080
export ZENML_STORE_USERNAME=nexus-admin
export ZENML_STORE_PASSWORD=<ZENML_PASSWORD>
```

Then run a pipeline:

```python
from zenml import pipeline, step

@step
def make_numbers() -> list[int]:
    return [1, 2, 3]

@step
def total(numbers: list[int]) -> int:
    return sum(numbers)

@pipeline
def demo():
    total(make_numbers())

demo()
```

The run, both steps and their artifacts appear in the dashboard at `https://zenml.<domain>`. The client keeps the artifacts themselves in the artifact store of its active ZenML stack, by default a local folder on the machine running the pipeline. The server stores only the metadata.

Tested:
- the server activated itself;
- `nexus-admin` logged in as an admin;
- the pipeline above ran against the server from a client container and returned 6;
- anonymous requests refused (`401`);
- a wrong password refused (`401`);
- a second activation refused (`403`);
- the run was still listed after a restart.

**Not tried here:** logging in to the dashboard in a browser.

### Activation

A fresh ZenML server waits for its first visitor to activate it by creating the admin account. The stack sets `ZENML_SERVER_AUTO_ACTIVATE` with `nexus-admin` and the generated password, so the server activates itself on the first start and refuses any later activation.

### Why the image is built here

The published `zenmldocker/zenml-server` images are amd64 only. The stack builds the same release, `zenml[server]==0.98.0`, on `python:3.12.13-slim`, which works on amd64 and arm64. It follows the server stage of ZenML's own Dockerfile: a non-root user, the config under `/zenml/.zenconfig`, and uvicorn behind the proxy.

Upstream's image also installs the extras for cloud secret stores and orchestrators (AWS, GCP, Azure). They are left out, because the server keeps its secrets in its own encrypted SQL store.

### Settings

- **A fixed JWT signing key.** Without one, ZenML generates a new key at every start and logs everyone out.
- **An encryption key for the secrets store.** Without one, secrets are stored unencrypted.
- **Analytics** are off. The upstream image turns them on.

### Persistence

Runs, artifact metadata, users and the encrypted secrets are in SQLite in `zenml-data`.

- **`rebuild` (default): they do not survive a teardown.** ZenML is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
