/**
 * Get workflow status
 * GET /api/status
 * 
 * Returns the current infrastructure state based on GitHub Actions workflow runs.
 * More robust than before - uses workflow file paths instead of name matching.
 */
export async function onRequestGet(context) {
  const { env, request } = context;
  
  // Validate environment variables
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return new Response(JSON.stringify({ 
      success: false, 
      error: 'Missing required environment variables' 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Workflow file paths (more reliable than name matching)
  const WORKFLOW_PATHS = {
    deploy: 'deploy.yml',
    teardown: 'teardown.yml',
    destroy: 'destroy-all.yml'
  };

  try {
    const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs?per_page=20`;
    
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Nexus-Stack-Control-Panel',
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
      deploy: null,
      teardown: null,
      destroy: null,
    };

    for (const run of data.workflow_runs) {
      const workflowPath = run.path || run.workflow_id || '';
      const workflowName = run.name || '';
      
      // Match by path first (most reliable), then fallback to name
      if (!workflows.deploy && (
        workflowPath.includes(WORKFLOW_PATHS.deploy) || 
        workflowName.includes('Deploy')
      )) {
        workflows.deploy = run;
      } else if (!workflows.teardown && (
        workflowPath.includes(WORKFLOW_PATHS.teardown) || 
        workflowName.includes('Teardown')
      )) {
        workflows.teardown = run;
      } else if (!workflows.destroy && (
        workflowPath.includes(WORKFLOW_PATHS.destroy) || 
        workflowName.includes('Destroy')
      )) {
        workflows.destroy = run;
      }
    }

    // Determine infrastructure state based on recent runs
    let infraState = 'unknown';
    let inProgress = false;

    // Check if any workflow is currently running
    const allRuns = [workflows.deploy, workflows.teardown, workflows.destroy].filter(Boolean);
    const runningWorkflow = allRuns.find(r => 
      r && (r.status === 'in_progress' || r.status === 'queued')
    );
    
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
        const lastPath = lastRun.path || lastRun.workflow_id || '';
        const lastName = lastRun.name || '';
        
        if (lastPath.includes(WORKFLOW_PATHS.deploy) || lastName.includes('Deploy')) {
          infraState = 'deployed';
        } else if (lastPath.includes(WORKFLOW_PATHS.teardown) || lastName.includes('Teardown')) {
          infraState = 'torn-down';
        } else if (lastPath.includes(WORKFLOW_PATHS.destroy) || lastName.includes('Destroy')) {
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
