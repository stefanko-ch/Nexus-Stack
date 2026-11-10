---
title: "Evidently"
---

## Evidently

![Evidently](https://img.shields.io/badge/Evidently-ED0400?logoColor=white)

**Data quality, drift and ML model monitoring**

Evidently computes reports on datasets:
- data quality: missing values, ranges, types;
- drift: between a reference batch and a current one, for data and for predictions;
- model metrics: classification and regression;
- LLM evals.

The service stores those reports per project and plots them over time. Next to [Soda](soda.md) and [TestGen](testgen.md), which check data at one point in time, it shows how data and models change from batch to batch.

| Setting | Value |
|---------|-------|
| URL | `https://evidently.<domain>` |
| In-cluster | `http://evidently:8000` |
| Login | None — Cloudflare Access is the gate |
| Write secret | Generated per deployment (Infisical folder `evidently`) |
| Persistence | Docker volume `evidently-workspace` |
| Licence | Apache-2.0 |
| Website | [evidentlyai.com](https://www.evidentlyai.com) |

### First steps

From a notebook (`pip install evidently==0.7.23`, the service's version), compute a report and push it:

```python
import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset
from evidently.ui.workspace import RemoteWorkspace

ws = RemoteWorkspace("http://evidently:8000", secret="<EVIDENTLY_SECRET>")
project = ws.create_project("orders")

reference = pd.DataFrame({"amount": range(100)})
current = pd.DataFrame({"amount": range(50, 150)})
run = Report([DataDriftPreset()]).run(current_data=current, reference_data=reference)
ws.add_run(project.id, run)
```

Open `https://evidently.<domain>` and pick the project. Each later run adds a point to the plots.

**The web UI cannot write.** It sends no secret, so writing from the browser fails with `Status: 403, Not enough permissions`. This was observed for creating a project. Create projects and push runs from Python as above.

Tested:
- the snippet above pushed a report;
- without the secret and with a wrong one, creating a project failed (`Not enough permissions`);
- the project was kept across a restart.

### Access

The service has no user accounts.
- **Writing** (creating projects, adding runs, deleting) needs the secret in the `evidently-secret` header, which `RemoteWorkspace` sends. Without it, any container on `app-network` could change or delete projects.
- **Reading has no check at all.** In the browser, Cloudflare Access is the only gate. On the server network, any container can read the reports. Evidently is in the list of stacks without their own login, which keeps it from ever getting a public firewall port.

Evidently's usage events, sent to its own server by default, are off (`DO_NOT_TRACK`).

### Resources

It used about 215 MB. Large reports with many columns are computed in the client, not in the service.

### Persistence

Projects and runs are files in `evidently-workspace`.

- **`rebuild` (default): they do not survive a teardown.** Evidently is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
