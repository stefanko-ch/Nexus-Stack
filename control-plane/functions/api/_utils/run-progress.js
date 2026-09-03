/**
 * Turn a GitHub Actions run + its jobs into "Step N of M".
 *
 * Pure: no I/O, no clock, no globals. The Control Plane has no JavaScript
 * test runner, so purity is the only testability this logic gets — every
 * rule below can be exercised in a Node REPL against a saved
 * `GET /actions/runs/{id}/jobs` payload, and was.
 *
 * WHAT THE JOBS API ACTUALLY RETURNS, since two of these surprised us:
 *
 *   - Housekeeping steps are in the list. `Set up job`, one `Post <name>`
 *     per action with a post hook (checkout, setup-node, the caches…),
 *     and `Complete job`. A workflow declaring 30 steps comes back as 37.
 *     They stay in N and M so the numbers match what the operator sees on
 *     "View in GitHub"; the UI dims them.
 *   - `step.number` is NOT a 1..M index. The post-steps of a 37-step job
 *     are numbered 61, 62, 63. `number` is what GitHub's step anchor
 *     (`#step:<number>:1`) wants; `index` below is ours, contiguous across
 *     jobs, and is what N/M is built from. Never mix them.
 *   - A queued job has `steps: []` until a runner picks it up. In a
 *     reusable-workflow run (spin-up-snapshot.yml) the second job does not
 *     appear at all until the first finishes, so M can grow mid-run.
 *
 * FAILURE IS THE FAILURE POINT, NOT THE LAST STEP THAT RAN. `if: always()`
 * steps — Close SSH port, Collect debug logs, every Post-step, Complete
 * job — run after a failure. "Last step that ran" is therefore always the
 * final one, and a failed run would fill the bar to 100%. The bar answers
 * "how far did it get": the first `failure` step. What ran afterwards is
 * visible, ticked, in the details list — that is where it is honest, not
 * on the bar.
 */

const HOUSEKEEPING = /^(Set up job|Post |Complete job)/;

/** Anything not started and not finished, whatever GitHub calls it today. */
function isPending(status) {
  return status !== 'in_progress' && status !== 'completed';
}

function durationBetween(startedAt, completedAt) {
  if (!startedAt || !completedAt) return null;
  const ms = Date.parse(completedAt) - Date.parse(startedAt);
  return Number.isFinite(ms) ? Math.max(0, ms) : null;
}

/**
 * @param {object|null} run   one item of `workflow_runs`, or the run object
 * @param {object|null} jobs  the `/actions/runs/{id}/jobs` payload
 */
export function deriveProgress(run, jobs) {
  const rawJobs = jobs && Array.isArray(jobs.jobs) ? jobs.jobs : [];

  const flat = [];
  const outJobs = [];
  let index = 0;

  for (const job of rawJobs) {
    const rawSteps = Array.isArray(job.steps) ? job.steps : [];
    const steps = [];
    for (const s of rawSteps) {
      index += 1;
      const step = {
        index,
        number: typeof s.number === 'number' ? s.number : null,
        name: typeof s.name === 'string' ? s.name : '',
        jobName: typeof job.name === 'string' ? job.name : '',
        status: typeof s.status === 'string' ? s.status : 'queued',
        conclusion: typeof s.conclusion === 'string' ? s.conclusion : null,
        startedAt: s.started_at || null,
        completedAt: s.completed_at || null,
        durationMs: durationBetween(s.started_at, s.completed_at),
        housekeeping: HOUSEKEEPING.test(typeof s.name === 'string' ? s.name : ''),
        htmlUrl: job.html_url && typeof s.number === 'number'
          ? `${job.html_url}#step:${s.number}:1`
          : null,
      };
      flat.push(step);
      steps.push(step);
    }
    outJobs.push({
      name: typeof job.name === 'string' ? job.name : '',
      status: typeof job.status === 'string' ? job.status : 'queued',
      conclusion: typeof job.conclusion === 'string' ? job.conclusion : null,
      startedAt: job.started_at || null,
      completedAt: job.completed_at || null,
      htmlUrl: job.html_url || null,
      steps,
    });
  }

  const total = flat.length;
  const completed = flat.filter((s) => s.status === 'completed').length;
  const skipped = flat.filter((s) => s.conclusion === 'skipped').length;
  const failed = flat.filter((s) => s.conclusion === 'failure').length;

  const runStatus = run && typeof run.status === 'string' ? run.status : 'queued';
  const runConclusion = run && typeof run.conclusion === 'string' ? run.conclusion : null;
  const runDone = runStatus === 'completed';

  // `current`: the step in progress, else the first one still to come
  // (labelled "starting" so the UI does not claim it has begun).
  const running = flat.find((s) => s.status === 'in_progress') || null;
  const next = running ? null : flat.find((s) => isPending(s.status)) || null;
  let current = null;
  if (running) {
    current = { index: running.index, name: running.name, jobName: running.jobName, startedAt: running.startedAt, starting: false };
  } else if (next && !runDone) {
    current = { index: next.index, name: next.name, jobName: next.jobName, startedAt: null, starting: true };
  }

  // Indeterminate: nothing to count yet. Either no job has steps (queued
  // behind the concurrency group, or no runner yet), or the job about to
  // run has not reported its steps — never render "0 of 0".
  let indeterminate = false;
  let waitingFor = null;
  if (!runDone) {
    if (total === 0) {
      indeterminate = true;
    } else if (!running) {
      const waitingJob = outJobs.find((j) => isPending(j.status) && j.steps.length === 0);
      if (waitingJob) {
        indeterminate = true;
        waitingFor = waitingJob.name || null;
      }
    }
  }

  const firstFailure = flat.find((s) => s.conclusion === 'failure') || null;
  const firstCancelled = flat.find((s) => s.conclusion === 'cancelled') || null;
  const failedAt = firstFailure
    ? { index: firstFailure.index, name: firstFailure.name, jobName: firstFailure.jobName, htmlUrl: firstFailure.htmlUrl }
    : null;
  const cancelledAt = runConclusion === 'cancelled'
    ? (firstCancelled
      ? { index: firstCancelled.index, name: firstCancelled.name, jobName: firstCancelled.jobName }
      : null)
    : null;

  let percent = 0;
  if (total > 0) {
    if (runDone && runConclusion === 'success') {
      percent = 100;
    } else if (runDone && failedAt) {
      percent = Math.round((failedAt.index / total) * 100);
    } else if (runDone && cancelledAt) {
      percent = Math.round((cancelledAt.index / total) * 100);
    } else if (runDone) {
      // completed with a conclusion that named no step (timed_out, skipped
      // job): show what finished, do not pretend it is 100.
      percent = Math.round((completed / total) * 100);
    } else {
      percent = Math.round((completed / total) * 100);
    }
  }

  // "Work began" is the earliest job start, not run.created_at — the run
  // can sit behind `concurrency: group: infrastructure` for minutes and
  // that wait is reported separately by the UI.
  const jobStarts = outJobs.map((j) => j.startedAt).filter(Boolean).sort();
  const startedAt = jobStarts.length > 0 ? jobStarts[0] : (run && run.run_started_at) || null;

  return {
    runId: run && typeof run.id === 'number' ? run.id : null,
    runNumber: run && typeof run.run_number === 'number' ? run.run_number : null,
    status: runStatus,
    conclusion: runConclusion,
    htmlUrl: (run && run.html_url) || null,
    createdAt: (run && run.created_at) || null,
    startedAt,
    percent,
    indeterminate,
    waitingFor,
    current,
    failedAt,
    cancelledAt,
    totals: { steps: total, completed, skipped, failed },
    jobs: outJobs,
  };
}
