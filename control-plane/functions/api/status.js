/**
 * Get workflow status
 * GET /api/status
 *
 * Returns the current infrastructure state based on GitHub Actions workflow runs.
 * More robust than before - uses workflow file paths instead of name matching.
 */
import { fetchWithTimeout } from './_utils/fetch-with-timeout.js';
import { ALL_SPINUP_WORKFLOWS, ALL_TEARDOWN_WORKFLOWS } from './_utils/workflow-selection.js';

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

  try {
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs?per_page=100`;

    const response = await fetchWithTimeout(url, {
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Plane',
      },
    });

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

    // Find the most recent run for each workflow type
    // Use workflow path (more reliable) or fallback to name
    const workflows = {
      initialSetup: null,
      setup: null,
      spinUp: null,
      teardown: null,
      destroy: null,
    };

    for (const run of data.workflow_runs) {
      const workflowPath = run.path || run.workflow_id || '';
      const workflowName = run.name || '';

      // Match by path first (most reliable), then fallback to name
      // Initial Setup includes spin-up, so count it as a successful deployment
      if (!workflows.initialSetup && (
        matchesPath(workflowPath, WORKFLOW_PATHS.initialSetup) ||
        workflowName.includes('Initial Setup')
      )) {
        workflows.initialSetup = run;
      } else if (!workflows.setup && (
        matchesPath(workflowPath, WORKFLOW_PATHS.setup) ||
        workflowName.includes('Setup') && !workflowName.includes('Initial')
      )) {
        workflows.setup = run;
      } else if (!workflows.spinUp && (
        matchesPath(workflowPath, WORKFLOW_PATHS.spinUp) ||
        workflowName.includes('Spin Up') ||
        workflowName.includes('Spin-Up')
      )) {
        workflows.spinUp = run;
      } else if (!workflows.teardown && (
        matchesPath(workflowPath, WORKFLOW_PATHS.teardown) ||
        workflowName.includes('Teardown')
      )) {
        workflows.teardown = run;
      } else if (!workflows.destroy && (
        matchesPath(workflowPath, WORKFLOW_PATHS.destroy) ||
        workflowName.includes('Destroy')
      )) {
        workflows.destroy = run;
      }
    }

    // Determine infrastructure state based on recent runs
    let infraState = 'unknown';
    let inProgress = false;

    // Check if any workflow is currently running
    const allRuns = [workflows.initialSetup, workflows.setup, workflows.spinUp, workflows.teardown, workflows.destroy].filter(Boolean);
    const runningWorkflow = allRuns.find(r =>
      r && (r.status === 'in_progress' || r.status === 'queued')
    );

    if (runningWorkflow) {
      inProgress = true;
      infraState = 'running';
    } else {
      // Find the most recent completed workflow
      // Include initialSetup as it contains spin-up
      const completedRuns = [workflows.initialSetup, workflows.spinUp, workflows.teardown, workflows.destroy]
        .filter(r => r && r.conclusion === 'success')
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

      if (completedRuns.length > 0) {
        const lastRun = completedRuns[0];
        const lastPath = lastRun.path || lastRun.workflow_id || '';
        const lastName = lastRun.name || '';

        // Initial Setup or Spin Up means infrastructure is deployed
        if (matchesPath(lastPath, WORKFLOW_PATHS.initialSetup) || lastName.includes('Initial Setup') ||
            matchesPath(lastPath, WORKFLOW_PATHS.spinUp) || lastName.includes('Spin Up') || lastName.includes('Spin-Up')) {
          infraState = 'deployed';
        } else if (matchesPath(lastPath, WORKFLOW_PATHS.teardown) || lastName.includes('Teardown')) {
          infraState = 'torn-down';
        } else if (matchesPath(lastPath, WORKFLOW_PATHS.destroy) || lastName.includes('Destroy')) {
          infraState = 'destroyed';
        }
      }
    }

    return new Response(JSON.stringify({
      success: true,
      infraState,
      inProgress,
      workflows: {
        initialSetup: workflows.initialSetup ? {
          status: workflows.initialSetup.status,
          conclusion: workflows.initialSetup.conclusion,
          updatedAt: workflows.initialSetup.updated_at,
          url: workflows.initialSetup.html_url,
        } : null,
        setup: workflows.setup ? {
          status: workflows.setup.status,
          conclusion: workflows.setup.conclusion,
          updatedAt: workflows.setup.updated_at,
          url: workflows.setup.html_url,
        } : null,
        spinUp: workflows.spinUp ? {
          status: workflows.spinUp.status,
          conclusion: workflows.spinUp.conclusion,
          updatedAt: workflows.spinUp.updated_at,
          url: workflows.spinUp.html_url,
        } : null,
        teardown: workflows.teardown ? {
          status: workflows.teardown.status,
          conclusion: workflows.teardown.conclusion,
          updatedAt: workflows.teardown.updated_at,
          url: workflows.teardown.html_url,
        } : null,
        destroy: workflows.destroy ? {
          status: workflows.destroy.status,
          conclusion: workflows.destroy.conclusion,
          updatedAt: workflows.destroy.updated_at,
          url: workflows.destroy.html_url,
        } : null,
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
      error: 'Internal server error'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
