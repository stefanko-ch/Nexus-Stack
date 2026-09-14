"""MLflow tracking from a Marimo notebook, with the connection made once.

Usage in a Marimo cell
----------------------

    from _nexus_mlflow import get_client, experiment

    experiment("housing-prices")        # creates it if absent
    import mlflow
    with mlflow.start_run():
        mlflow.log_param("degree", 2)
        mlflow.log_metric("rmse", 0.41)

    client = get_client()               # for reading runs back
    runs = client.search_runs(experiment_ids=[experiment("housing-prices")])

Connection defaults
-------------------

``MLFLOW_TRACKING_URI`` is set for you by the Marimo stack and points at
``http://mlflow:5000`` — the in-cluster address, not the public hostname.
Two separate things make the public one fail, and the second is the one that
will fool you:

1. ``https://mlflow.<domain>`` sits behind Cloudflare Access, which answers an
   API client with an HTML login page rather than JSON.
2. MLflow 3.x validates the ``Host`` header and rejects anything it was not
   told to expect with ``403 Invalid Host header - possible DNS rebinding
   attack detected``. The server allows ``mlflow:5000`` and its own public
   hostname; a request arriving under any other name is refused even from
   inside the network.

``mlflow`` itself reads ``MLFLOW_TRACKING_URI`` without being told to, so
plain ``import mlflow`` already talks to the right server. This module exists
for the two things that are not automatic: a cached ``MlflowClient`` for
reading runs back, and ``experiment()``, which is idempotent where
``mlflow.create_experiment`` is not.

Why the client is cached
------------------------

Marimo's reactive graph re-runs cells when their inputs change, but
module-level state survives. A fresh ``MlflowClient`` per cell run is cheap
but not free — it re-resolves the tracking URI and opens a new connection
pool — and holding one makes run-comparison cells noticeably quicker.

Call ``reset_client()`` after changing ``MLFLOW_TRACKING_URI`` in the process;
the cache is keyed on nothing, so it would otherwise keep handing back the
client built from the old value.

What this notebook environment can and cannot do
------------------------------------------------

The Marimo image installs **mlflow-skinny**, the tracking client. Logging
params, metrics, artifacts, tags and registry entries all work. What is absent
is scikit-learn and scipy: full MLflow pulls them in as hard dependencies and
costs 465 MB against skinny's 78 MB, which is not a good trade for an image
that already carries PySpark.

In practice that means ``mlflow.sklearn.log_model(...)`` has no model to be
handed, because you cannot fit one here. Log the metrics and the artifacts
instead — which is the part of MLflow this deployment is for — or add
scikit-learn to ``stacks/marimo/Dockerfile`` deliberately.
"""

from __future__ import annotations

import os
from typing import Optional

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import RESOURCE_ALREADY_EXISTS, ErrorCode
from mlflow.tracking import MlflowClient

# Mirrors stacks/marimo/docker-compose.yml, so a notebook works unchanged on a
# default deployment even if the variable is missing. Port 5000 is the
# container's; the host publishes 5001.
DEFAULT_TRACKING_URI = "http://mlflow:5000"

_client: Optional[MlflowClient] = None


def tracking_uri() -> str:
    """The tracking server this notebook talks to."""
    return os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)


def get_client() -> MlflowClient:
    """Return a process-wide ``MlflowClient``, creating it on first call."""
    global _client
    if _client is None:
        mlflow.set_tracking_uri(tracking_uri())
        _client = MlflowClient()
    return _client


def reset_client() -> None:
    """Drop the cached client so the next call rebuilds it."""
    global _client
    _client = None


def experiment(name: str) -> str:
    """Return the id of ``name``, creating the experiment if it does not exist.

    ``mlflow.create_experiment`` raises once the experiment is there, which
    makes a notebook cell fail on its second run for no useful reason. This is
    the idempotent form, and it also activates the experiment so a following
    ``mlflow.start_run()`` lands in it.

    The look-then-create is not atomic, and on a shared tracking server that
    gap is reachable rather than theoretical: a class starting the same
    notebook at the same time has several clients checking for the same
    missing experiment within the same second. The loser of that race gets
    ``RESOURCE_ALREADY_EXISTS``, which is not an error here — somebody else
    created exactly what this call wanted. Look it up again and carry on.
    """
    client = get_client()
    existing = client.get_experiment_by_name(name)
    if existing is not None:
        exp_id = existing.experiment_id
    else:
        try:
            exp_id = client.create_experiment(name)
        except MlflowException as exc:
            # `exc.error_code` is the NAME, not the number. Measured against
            # 3.16.0: the attribute is the string 'RESOURCE_ALREADY_EXISTS'
            # while the imported constant is the int 3001, so comparing them
            # directly is always unequal and this handler would re-raise every
            # time while looking correct.
            if exc.error_code != ErrorCode.Name(RESOURCE_ALREADY_EXISTS):
                raise
            raced = client.get_experiment_by_name(name)
            if raced is None:  # pragma: no cover - would mean it vanished again
                raise
            exp_id = raced.experiment_id
    mlflow.set_experiment(experiment_id=exp_id)
    return str(exp_id)
