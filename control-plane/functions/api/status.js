/**
 * Get workflow status
 * GET /api/status[?progress_for=<run id>]
 *
 * Returns the current infrastructure state based on GitHub Actions workflow
 * runs, and — while a lifecycle run is in progress — its step-by-step
 * progress ("Step N of M") from the jobs API.
 *
 * ONE endpoint on purpose. The GitHub rate limit (5000/h) is per account,
 * shared by every token of it. A second browser request per poll would
 * double the spend for the same picture; folding the jobs fetch in here
 * means one request from the browser and at most two to GitHub, and only
 * the second while something is actually running. It also means the
 * browser never supplies a run id to fetch — see `progress_for` below for
 * the one narrow exception.
 *
 * `progress_for` exists so the dashboard can render the FINAL state of a
 * run that just finished (100% green, or red at the failed step) — the
 * status alone would drop it the moment `inProgress` turns false. The id
 * is accepted only if it is one this endpoint itself selected; anything
 * else is ignored, not fetched.
 *
 * No `requireSameOrigin` here: that guard requires a JSON Content-Type,
 * which a browser GET never sends, and it exists for state-changing
 * endpoints. Reads are gated by Cloudflare Access like every other GET.
 */
import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { ALL_SPINUP_WORKFLOWS, ALL_TEARDOWN_WORKFLOWS } from './_utils/workflow-selection.js';
import { deriveProgress } from './_utils/run-progress.js';
import { readDispatchMarkers, DISPATCH_GRACE_MS, DISPATCH_SKEW_MS } from './_utils/dispatch-marker.js';

const FAMILY_ORDER = ['initialSetup', 'setup', 'spinUp', 'teardown', 'destroy'];

function githubHeaders(token) {
  return {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'Nexus-Stack-Control-Plane',
  };
}

/** The wire shape for one run. Only fields the UI needs; never the raw run. */
function summarise(run) {
  if (!run) return null;
  return {
    id: run.id,
    runNumber: run.run_number,
    status: run.status,
    conclusion: run.conclusion,
    createdAt: run.created_at,
    updatedAt: run.updated_at,
    event: run.event,
    url: run.html_url,
  };
}

/**
 * Jobs for one run, derived into progress. Never throws: a failure to
 * look is reported as `unavailable`, not as "no steps" — the UI then says
 * the step list could not be read instead of showing an empty one.
 */
async function fetchProgress(env, run) {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${run.id}/jobs?per_page=100`;
  try {
    const response = await fetchWithTimeout(url, { headers: githubHeaders(env.GITHUB_TOKEN) });
    if (!response.ok) {
      // Status code only. The body is GitHub's, but this project does not
      // forward API bodies it has not looked at.
      console.error(`GitHub jobs API error: ${response.status}`);
      return { ...deriveProgress(run, null), unavailable: true };
    }
    return deriveProgress(run, await response.json());
  } catch (error) {
    console.error('GitHub jobs fetch failed:', error && error.name);
    return { ...deriveProgress(run, null), unavailable: true };
  }
}

export async function onRequestGet(context) {
  const { env, request } = context;

  // Validate environment variables
  const missing = [];
  if (!env.GITHUB_TOKEN) missing.push('GITHUB_TOKEN');
  if (!env.GITHUB_OWNER) missing.push('GITHUB_OWNER');
  if (!env.GITHUB_REPO) missing.push('GITHUB_REPO');

  if (missing.length > 0) {
    return new Response(JSON.stringify({
      success: false,
      error: `Missing required environment variables: ${missing.join(', ')}. Configure them in Cloudflare Dashboard: Pages → Settings → Environment Variables → Secrets, or run: make setup-control-plane-secrets`
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Workflow file paths (more reliable than name matching).
  //
  // The two lifecycle entries are LISTS because a stack may be on either
  // pair — see _utils/workflow-selection.js. Substring matching does not
  // cover this on its own: 'spin-up-snapshot.yml'.includes('spin-up.yml')
  // is false, so the snapshot runs would fall through to name matching
  // and detection would depend on the workflow's display name.
  const WORKFLOW_PATHS = {
    initialSetup: ['initial-setup.yaml'],
    setup: ['setup-control-plane.yaml'],
    spinUp: ALL_SPINUP_WORKFLOWS,
    teardown: ALL_TEARDOWN_WORKFLOWS,
    destroy: ['destroy-all.yml']
  };
  const matchesPath = (path, candidates) => candidates.some((c) => path.includes(c));

  // Which family a run belongs to: path first (most reliable), then name.
  // Initial Setup includes spin-up, so it counts as a successful deployment.
  const classify = (run) => {
    // Strictly a string. `workflow_id` used to be the fallback here, and
    // it is a NUMBER — `path.includes(...)` on it throws a TypeError and
    // takes the whole endpoint down. It could not have matched a filename
    // substring anyway.
    const path = typeof run.path === 'string' ? run.path : '';
    const name = typeof run.name === 'string' ? run.name : '';
    if (matchesPath(path, WORKFLOW_PATHS.initialSetup) || name.includes('Initial Setup')) return 'initialSetup';
    if (matchesPath(path, WORKFLOW_PATHS.setup) || (name.includes('Setup') && !name.includes('Initial'))) return 'setup';
    if (matchesPath(path, WORKFLOW_PATHS.spinUp) || name.includes('Spin Up') || name.includes('Spin-Up')) return 'spinUp';
    if (matchesPath(path, WORKFLOW_PATHS.teardown) || name.includes('Teardown')) return 'teardown';
    if (matchesPath(path, WORKFLOW_PATHS.destroy) || name.includes('Destroy')) return 'destroy';
    return null;
  };

  try {
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs?per_page=100`;

    const response = await fetchWithTimeout(url, { headers: githubHeaders(env.GITHUB_TOKEN) });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`GitHub API error: ${response.status} - ${errorText}`);

      return new Response(JSON.stringify({
        success: false,
        error: `Failed to fetch workflow status: ${response.status}`
      }), {
        status: response.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Surfaced so the client can slow down before the account runs dry —
    // the limit is shared with every other token of this GitHub user.
    //
    // The null check is not defensive noise: `Number(null)` is 0, and a
    // finite 0 reads as "no budget left", so a missing header would slow
    // every poll to the low-budget cadence — including mid-run.
    const remainingHeader = response.headers.get('x-ratelimit-remaining');
    const remainingValue = remainingHeader === null ? NaN : Number(remainingHeader);
    const rateLimitRemaining = Number.isFinite(remainingValue) ? remainingValue : null;

    const data = await response.json();

    if (!data.workflow_runs || !Array.isArray(data.workflow_runs)) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Invalid response from GitHub API'
      }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Dispatches that have not shown up as runs yet. Runs of a marked
    // family created before its dispatch are ignored while the marker is
    // fresh, so the previous run cannot be mistaken for the new one — the
    // race dispatch-marker.js describes. Markers are per family: a
    // teardown dispatched while a setup is still pending must not erase
    // the setup's protection.
    const now = Date.now();
    const markers = await readDispatchMarkers(env.NEXUS_DB, now);
    const cutoffFor = (family) =>
      markers[family] ? markers[family].at - DISPATCH_SKEW_MS : null;
    const predatesDispatch = (family, run) => {
      const cutoff = cutoffFor(family);
      return cutoff !== null && Date.parse(run.created_at) < cutoff;
    };

    // Newest run per family. The list is newest-first, so first match wins.
    const workflows = { initialSetup: null, setup: null, spinUp: null, teardown: null, destroy: null };
    for (const run of data.workflow_runs) {
      const family = classify(run);
      if (!family || workflows[family]) continue;
      if (predatesDispatch(family, run)) continue;
      workflows[family] = run;
    }

    // Is anything running?
    let runningFamily = null;
    for (const family of FAMILY_ORDER) {
      const r = workflows[family];
      if (r && (r.status === 'in_progress' || r.status === 'queued')) {
        runningFamily = family;
        break;
      }
    }
    const runningWorkflow = runningFamily ? workflows[runningFamily] : null;

    // Dispatched, but GitHub has not listed the run yet. Reported for the
    // oldest still-pending dispatch, so two in flight cannot hide one
    // another.
    let dispatching = false;
    let dispatchTimedOut = false;
    let dispatchedAt = null;
    let dispatchedWorkflow = null;
    const pending = FAMILY_ORDER
      .filter((family) => {
        if (!markers[family]) return false;
        const candidate = workflows[family];
        return !(candidate && Date.parse(candidate.created_at) >= cutoffFor(family));
      })
      .sort((a, b) => markers[a].at - markers[b].at);
    if (pending.length > 0) {
      const family = pending[0];
      dispatchedAt = new Date(markers[family].at).toISOString();
      dispatchedWorkflow = family;
      if (markers[family].ageMs <= DISPATCH_GRACE_MS) dispatching = true;
      else dispatchTimedOut = true;
    }

    // Determine infrastructure state based on recent runs
    let infraState = 'unknown';
    let inProgress = false;

    if (runningWorkflow || dispatching) {
      inProgress = true;
      infraState = 'running';
    } else {
      // Find the most recent completed workflow
      // Include initialSetup as it contains spin-up
      const completedRuns = [workflows.initialSetup, workflows.spinUp, workflows.teardown, workflows.destroy]
        .filter(r => r && r.conclusion === 'success')
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

      if (completedRuns.length > 0) {
        const lastFamily = classify(completedRuns[0]);
        // Initial Setup or Spin Up means infrastructure is deployed
        if (lastFamily === 'initialSetup' || lastFamily === 'spinUp') {
          infraState = 'deployed';
        } else if (lastFamily === 'teardown') {
          infraState = 'torn-down';
        } else if (lastFamily === 'destroy') {
          infraState = 'destroyed';
        }
      }
    }

    // Step progress: for the running run, or for the one just-finished run
    // the client asked about — and only if that id is one we selected.
    let progress = null;
    let progressFamily = null;
    if (runningWorkflow) {
      progress = await fetchProgress(env, runningWorkflow);
      progressFamily = runningFamily;
    } else {
      const requested = new URL(request.url).searchParams.get('progress_for');
      if (requested && /^\d{1,15}$/.test(requested)) {
        const wanted = Number(requested);
        const family = FAMILY_ORDER.find((f) => workflows[f] && workflows[f].id === wanted) || null;
        if (family) {
          progress = await fetchProgress(env, workflows[family]);
          progressFamily = family;
        }
      }
    }

    return new Response(JSON.stringify({
      success: true,
      infraState,
      inProgress,
      runningWorkflow: runningFamily,
      dispatching,
      dispatchTimedOut,
      dispatchedAt,
      dispatchedWorkflow,
      progress,
      progressFamily,
      rateLimitRemaining,
      workflows: {
        initialSetup: summarise(workflows.initialSetup),
        setup: summarise(workflows.setup),
        spinUp: summarise(workflows.spinUp),
        teardown: summarise(workflows.teardown),
        destroy: summarise(workflows.destroy),
      },
    }), {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (error) {
    console.error('Status endpoint error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Failed to fetch workflow status'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
