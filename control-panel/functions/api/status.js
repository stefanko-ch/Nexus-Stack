/**
 * Get workflow status
 * GET /api/status
 */
export async function onRequestGet(context) {
  const { env } = context;
  
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs?per_page=10`;
  
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'Nexus-Stack-Control-Panel',
    },
  });

  if (!response.ok) {
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Failed to fetch workflow status' 
    }), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const data = await response.json();
  
  // Find the most recent run for each workflow type
  const workflows = {
    deploy: null,
    teardown: null,
    destroy: null,
  };

  for (const run of data.workflow_runs) {
    if (run.name.includes('Deploy') && !workflows.deploy) {
      workflows.deploy = run;
    } else if (run.name.includes('Teardown') && !workflows.teardown) {
      workflows.teardown = run;
    } else if (run.name.includes('Destroy') && !workflows.destroy) {
      workflows.destroy = run;
    }
  }

  // Determine infrastructure state based on recent runs
  let infraState = 'unknown';
  let inProgress = false;

  // Check if any workflow is currently running
  const allRuns = [workflows.deploy, workflows.teardown, workflows.destroy].filter(Boolean);
  const runningWorkflow = allRuns.find(r => r && (r.status === 'in_progress' || r.status === 'queued'));
  
  if (runningWorkflow) {
    inProgress = true;
    infraState = 'running';
  } else {
    // Find the most recent completed workflow
    const completedRuns = allRuns
      .filter(r => r && r.conclusion === 'success')
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    
    if (completedRuns.length > 0) {
      const lastRun = completedRuns[0];
      if (lastRun.name.includes('Deploy')) {
        infraState = 'deployed';
      } else if (lastRun.name.includes('Teardown')) {
        infraState = 'torn-down';
      } else if (lastRun.name.includes('Destroy')) {
        infraState = 'destroyed';
      }
    }
  }

  return new Response(JSON.stringify({
    success: true,
    infraState,
    inProgress,
    workflows: {
      deploy: workflows.deploy ? {
        status: workflows.deploy.status,
        conclusion: workflows.deploy.conclusion,
        updatedAt: workflows.deploy.updated_at,
        url: workflows.deploy.html_url,
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
    headers: { 'Content-Type': 'application/json' },
  });
}
