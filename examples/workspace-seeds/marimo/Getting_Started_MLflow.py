"""Track an experiment: params, metrics, artifacts, and comparing runs.

Deliberately short: marimo reads only the first 512 bytes to decide a file
is a notebook, and prose above `import marimo` pushes the markers out of
that window. The introduction lives in the first cell instead.
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
        # Experiment tracking with MLflow

        A training run produces numbers you will want again later: which
        settings you used, how well it scored, and the files it left behind.
        Writing those into cell output loses them the moment you re-run the
        cell. MLflow is the place to put them instead.

        Three things go into a run, and they are not interchangeable:

        - **Parameters** are inputs you chose. They never change within a run.
        - **Metrics** are results you measured. They can be logged repeatedly,
          which is how a loss curve is recorded.
        - **Artifacts** are files — a plot, a CSV, a serialised model.

        The split matters because MLflow lets you *sort by metric* and *filter
        by parameter*, which is the whole point of logging them separately
        rather than as one blob of text.

        **Where this goes.** The tracking server keeps parameters and metrics
        in PostgreSQL, and pushes artifacts to Cloudflare R2 under the
        `mlflow/` prefix. Both survive a teardown. Your notebook never touches
        R2 itself — the server proxies every upload, so no object-storage
        credentials live in this container.

        Everything below is safe to run more than once.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1 — Point at the server

        `MLFLOW_TRACKING_URI` is already set for you by the Marimo stack, so
        `import mlflow` alone is enough to reach the right server. The helper
        below adds the two things that are not automatic: a cached client for
        reading runs back, and an `experiment()` that does not fail on its
        second call.
        """
    )
    return


@app.cell
def _():
    import mlflow

    from _nexus_mlflow import experiment, get_client, tracking_uri

    exp_id = experiment("getting-started")
    client = get_client()
    result = f"Tracking at {tracking_uri()} — experiment id {exp_id}"
    result
    return client, exp_id, experiment, mlflow, result, tracking_uri


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2 — Log a run

        The "model" here is a straight-line fit, computed with numpy. That is
        deliberate: this notebook is about the *tracking*, and a real learner
        would only add noise to what the run record looks like.

        Note the shape — `with mlflow.start_run()` opens the run and closes it
        on exit, whatever happens inside. A crashed cell still leaves a run
        marked FAILED rather than an open one.
        """
    )
    return


@app.cell
def _(exp_id, mlflow):
    import os
    import tempfile

    import numpy as np
    import pandas as pd

    def fit_and_log(degree: int) -> str:
        """Fit a polynomial of `degree`, log what it took and what it scored."""
        rng = np.random.default_rng(0)
        x = np.arange(40.0)
        y = 0.9 * x + 0.05 * x**2 + rng.normal(0, 6, x.size)

        with mlflow.start_run(experiment_id=exp_id) as run:
            coeffs = np.polyfit(x, y, degree)
            predicted = np.polyval(coeffs, x)
            rmse = float(np.sqrt(((y - predicted) ** 2).mean()))

            mlflow.log_params({"degree": degree, "n_points": int(x.size)})
            mlflow.log_metric("rmse", rmse)

            # An artifact: the fitted curve next to the data, as a CSV a
            # colleague can open without this notebook.
            path = os.path.join(tempfile.mkdtemp(), f"fit_degree_{degree}.csv")
            pd.DataFrame({"x": x, "observed": y, "predicted": predicted}).to_csv(
                path, index=False
            )
            mlflow.log_artifact(path)

            return run.info.run_id

    run_id = fit_and_log(2)
    run_summary = f"Logged run {run_id[:12]}…"
    run_summary
    return (
        fit_and_log,
        np,
        os,
        pd,
        run_id,
        run_summary,
        tempfile,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3 — Log a second run, then compare

        One run tells you nothing. The comparison is the product.

        Re-running this cell adds more runs rather than replacing them, which
        is correct — a run is a historical record, not a variable. The table
        below sorts by RMSE, so the best fit is on top however many times you
        hit **Run all**.

        > Degrees 2 and 3 will score almost identically, and that is the
        > finding rather than a bug: the data was generated from a quadratic,
        > so the cubic term has nothing left to explain. Degree 1 is visibly
        > worse. Reading that off a sorted table is precisely what tracking
        > is for — the same three numbers in three cell outputs would tell you
        > nothing.
        """
    )
    return


@app.cell
def _(client, exp_id, fit_and_log, pd):
    for _degree in (1, 3):
        fit_and_log(_degree)

    runs = client.search_runs(experiment_ids=[exp_id], order_by=["metrics.rmse ASC"])
    comparison = pd.DataFrame(
        [
            {
                "run": r.info.run_id[:8],
                "degree": r.data.params.get("degree"),
                "rmse": round(r.data.metrics.get("rmse", float("nan")), 3),
                "status": r.info.status,
            }
            for r in runs
        ]
    )
    comparison
    return comparison, runs


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4 — Read an artifact back

        The file went to R2 through the tracking server. Getting it back does
        not need credentials either — the same proxy works in both directions.
        """
    )
    return


@app.cell
def _(client, pd, run_id):
    artifacts = [a.path for a in client.list_artifacts(run_id)]
    local_copy = client.download_artifacts(run_id, artifacts[0])
    recovered = pd.read_csv(local_copy).head()
    recovered
    return artifacts, local_copy, recovered


@app.cell
def _(mo):
    mo.md(
        r"""
        ## What to know before using this for real

        - **Open `https://mlflow.<your-domain>`** to see the same runs in the
          web UI, with charts and a side-by-side comparison view. The runs you
          just logged are under the `getting-started` experiment.
        - **Parameters are immutable, metrics are not.** Calling
          `log_metric("loss", x)` in a loop records a series and the UI plots
          it. Calling `log_param` twice with different values is an error.
        - **This image has no scikit-learn.** It installs `mlflow-skinny`, the
          tracking client — full MLflow pulls in scikit-learn, scipy and
          matplotlib and costs 465 MB against skinny's 78 MB. Logging works
          fully; fitting a real model does not. See `_nexus_mlflow.py`.
        - **Artifacts are files, and files cost money to move.** The R2 bucket
          is shared and egress is not free. A 2 GB checkpoint per run adds up
          across a cohort.
        - **Nothing here is private.** Cloudflare Access gates the browser, but
          any container on the network can write to any experiment. Treat the
          tracking server as a shared notebook, not a vault.
        """
    )
    return


if __name__ == "__main__":
    app.run()
