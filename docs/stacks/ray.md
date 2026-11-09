---
title: "Ray"
---

## Ray

![Ray](https://img.shields.io/badge/Ray-028CF0?logo=ray&logoColor=white)

**Distributed Python for data processing and machine learning**

Ray spreads Python work over many cores. `@ray.remote` turns a function into parallel tasks and a class into an actor. On top of that, Ray Data processes datasets in parallel, Ray Tune runs hyperparameter searches and Ray Serve serves models.

| Setting | Value |
|---------|-------|
| Default Port | `8265` (dashboard, bound to `127.0.0.1` on the host) |
| In-cluster | `ray://ray:10001` (Ray Client) |
| Suggested Subdomain | `ray` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Auth token, generated per deployment (Infisical folder `ray`) |
| Resources | 4 CPUs, 1 GB object store, 3 GB memory limit |
| Persistence | None |
| Website | [ray.io](https://www.ray.io) |
| Source | [GitHub](https://github.com/ray-project/ray) |

### Ray next to Spark

[Spark](spark.md) is the engine for SQL and DataFrames over large tables. Ray is the Python-native option: arbitrary Python functions, stateful actors and ML libraries, without a JVM.

### Authentication

Token authentication is on. The dashboard asks for the token once (`RAY_AUTH_TOKEN` from Infisical) and keeps it in a cookie. Every client sends it too. Without the token, the dashboard API answers `401` and the Ray Client cannot connect.

### Connecting from a notebook

The Ray Client needs **the same Ray version and the same Python minor version** as the cluster: `ray==2.60.0` on Python 3.12.

```bash
pip install "ray[client]==2.60.0"
export RAY_AUTH_MODE=token
export RAY_AUTH_TOKEN=<RAY_AUTH_TOKEN>
```

```python
import ray

ray.init("ray://ray:10001")

@ray.remote
def square(x):
    return x * x

print(sum(ray.get([square.remote(i) for i in range(10)])))  # 285
```

Tasks run on the Ray container, not in the notebook. Packages they import must be installed there, or passed per job with a [runtime environment](https://docs.ray.io/en/latest/ray-core/handling-dependencies.html).

### Resources

Ray would otherwise size itself to the whole server, so the head node is started with `--num-cpus=4` and a 1 GB object store, which lives in a 2 GB `/dev/shm`. Usage statistics are switched off.

### Persistence

None. Ray keeps no state worth keeping: job history and logs are gone after a restart, and results belong in storage such as MinIO or a database.
