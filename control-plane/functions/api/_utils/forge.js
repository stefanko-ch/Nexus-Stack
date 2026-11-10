/**
 * The forge this stack's repository lives on: GitHub, or a Forgejo.
 *
 * A stack deployed from GitHub talks to api.github.com. A stack that
 * Nexus-Conductor deployed lives on Conductor's Forgejo, and every call
 * that reached api.github.com there answered "Bad credentials" — the
 * Control Plane could not start, stop or even read its own workflows.
 *
 * Which one is decided by FORGE_URL alone. Unset means GitHub, so every
 * existing stack keeps its behaviour without a new setting. Set, it is the
 * forge's web address (https://forgejo.example.com); the API is
 * `${FORGE_URL}/api/v1`. It cannot be taken from the workflow's own
 * GITHUB_SERVER_URL: a Forgejo runner hands its jobs an internal address
 * that only exists inside the runner's network, and the Control Plane
 * runs on Cloudflare.
 *
 * A Forgejo behind Cloudflare Access needs a service token on every
 * request, FORGE_ACCESS_CLIENT_ID + FORGE_ACCESS_CLIENT_SECRET. Without
 * one, Access answers with a redirect to its login page, which is why
 * redirects are not followed here: following it would hand back a 200
 * with an HTML login form, and the caller would report a parse error
 * instead of the actual cause.
 *
 * This file is copied into worker/src/index.js, which Cloudflare uploads
 * as a single script and therefore cannot import it. Change both.
 */

import { fetchWithTimeout } from './fetch-with-timeout.js';

/** Forgejo's finished run states — DoneStatuses() in models/actions/status.go. */
const FORGEJO_DONE_STATUSES = new Set(['success', 'failure', 'cancelled', 'skipped']);

/**
 * @param {object} env
 * @returns {{ kind: 'github'|'forgejo', apiBase: string, webBase: string }}
 */
export function forgeConfig(env) {
  const forgeUrl = (env.FORGE_URL || '').trim().replace(/\/+$/, '');
  if (!forgeUrl) {
    return { kind: 'github', apiBase: 'https://api.github.com', webBase: 'https://github.com' };
  }
  return { kind: 'forgejo', apiBase: `${forgeUrl}/api/v1`, webBase: forgeUrl };
}

/** Request headers for the configured forge. */
export function forgeHeaders(env, extra = {}) {
  const { kind } = forgeConfig(env);
  if (kind === 'github') {
    return {
      'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'Nexus-Stack-Control-Plane',
      ...extra,
    };
  }
  const headers = {
    'Authorization': `token ${env.GITHUB_TOKEN}`,
    'Accept': 'application/json',
    'User-Agent': 'Nexus-Stack-Control-Plane',
    ...extra,
  };
  if (env.FORGE_ACCESS_CLIENT_ID && env.FORGE_ACCESS_CLIENT_SECRET) {
    headers['CF-Access-Client-Id'] = env.FORGE_ACCESS_CLIENT_ID;
    headers['CF-Access-Client-Secret'] = env.FORGE_ACCESS_CLIENT_SECRET;
  }
  return headers;
}

/** `/repos/{owner}/{repo}` on the configured forge's API. */
export function repoApiUrl(env, path) {
  return `${forgeConfig(env).apiBase}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}${path}`;
}

/** The repository's web page on the configured forge. */
export function repoWebUrl(env) {
  return `${forgeConfig(env).webBase}/${env.GITHUB_OWNER}/${env.GITHUB_REPO}`;
}

/**
 * fetch against the forge. On Forgejo, redirects are returned rather
 * than followed (see the file comment), so a 3xx reaches the caller as a
 * non-ok response. GitHub keeps following them: it redirects API calls
 * for a renamed repository, and those worked before this file existed.
 */
export function forgeFetch(env, url, options = {}, timeoutMs) {
  const redirect = forgeConfig(env).kind === 'forgejo' ? 'manual' : 'follow';
  return fetchWithTimeout(url, { redirect, ...options }, timeoutMs);
}

/**
 * A readable reason for a failed forge response. Reads the body only for
 * GitHub's and Forgejo's JSON `message`; anything else is reduced to the
 * status, so an HTML page never reaches the client.
 */
export async function forgeErrorMessage(response, fallback) {
  if (response.status >= 300 && response.status < 400) {
    return `${fallback}: the forge answered with a redirect (HTTP ${response.status}) — ` +
      'most likely Cloudflare Access in front of it refused the service token';
  }
  try {
    const body = await response.json();
    if (body && typeof body.message === 'string' && body.message) return body.message;
  } catch {
    // not JSON — fall through to the status
  }
  return `${fallback}: HTTP ${response.status}`;
}

/**
 * The HTTP status to answer the browser with for a failed forge call.
 * A redirect means the forge was not reached at all, which is a bad
 * gateway from the browser's side — passing a 302 through would make the
 * browser's fetch follow it to the Access login page.
 */
export function forgeErrorStatus(response) {
  return response.status >= 300 && response.status < 400 ? 502 : response.status;
}

/**
 * Dispatch a workflow on the default branch. Resolves to the raw
 * response; success is a 204 on both forges, as long as Forgejo is not
 * asked for run info.
 */
export function dispatchWorkflow(env, workflowFile, inputs = {}) {
  return forgeFetch(env, repoApiUrl(env, `/actions/workflows/${workflowFile}/dispatches`), {
    method: 'POST',
    headers: forgeHeaders(env, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ ref: 'main', inputs }),
  });
}

function isoOrNull(value) {
  const ms = value ? Date.parse(value) : NaN;
  return Number.isFinite(ms) && ms > 0 ? new Date(ms).toISOString() : null;
}

/**
 * One Forgejo ActionRun in the GitHub workflow_run shape the endpoints
 * read: `status` + `conclusion` instead of Forgejo's single `status`,
 * `path` built from `workflow_id` (the workflow's file name), and UTC
 * timestamps — Forgejo renders them in the server's own zone, and an
 * unset `started` as the Unix epoch.
 */
export function normalizeForgejoRun(run) {
  const raw = typeof run.status === 'string' ? run.status : '';
  let status = 'queued';
  let conclusion = null;
  if (FORGEJO_DONE_STATUSES.has(raw)) {
    status = 'completed';
    conclusion = raw;
  } else if (raw === 'running') {
    status = 'in_progress';
  }
  const created = isoOrNull(run.created);
  return {
    id: run.id,
    run_number: run.run_number ?? null,
    status,
    conclusion,
    created_at: created,
    updated_at: isoOrNull(run.updated) || isoOrNull(run.stopped) || created,
    run_started_at: isoOrNull(run.started) || created,
    event: run.event ?? null,
    html_url: run.html_url ?? null,
    path: typeof run.workflow_id === 'string' ? `.github/workflows/${run.workflow_id}` : '',
    // Deliberately empty. The endpoints fall back to matching words like
    // "Setup" or "Teardown" in a run's name when its path is unknown, and
    // Forgejo's nearest field, `title`, is usually a commit subject — any
    // run titled "fix: Setup …" would be counted as a setup. The path is
    // always present here, so the fallback is never needed.
    name: '',
  };
}

/**
 * The newest workflow runs, newest first, in GitHub's shape.
 *
 * @returns {Promise<{ ok: true, runs: object[], response: Response }
 *                  | { ok: false, response: Response }
 *                  | { ok: false, invalid: true, response: Response }>}
 */
export async function listWorkflowRuns(env, limit) {
  const { kind } = forgeConfig(env);
  // Forgejo applies `limit` only together with `page` — page 0 lists
  // everything — and caps it at its MAX_RESPONSE_ITEMS (50 by default).
  const query = kind === 'github' ? `?per_page=${limit}` : `?page=1&limit=${limit}`;
  const response = await forgeFetch(env, repoApiUrl(env, `/actions/runs${query}`), {
    headers: forgeHeaders(env),
  });
  if (!response.ok) return { ok: false, response };
  const data = await response.json();
  if (!data || !Array.isArray(data.workflow_runs)) return { ok: false, invalid: true, response };
  const runs = kind === 'github' ? data.workflow_runs : data.workflow_runs.map(normalizeForgejoRun);
  return { ok: true, runs, response };
}

/** How many runs one page holds. Forgejo caps a page at its MAX_RESPONSE_ITEMS, 50 by default. */
export function runsPageSize(env) {
  return forgeConfig(env).kind === 'github' ? 100 : 50;
}

/**
 * Workflow runs, newest first, read page by page until `enough(runs)` says the
 * caller has what it needs.
 *
 * One page is not a safe window. The list holds every workflow's runs, and CI
 * outnumbers lifecycle runs by far: a dozen merged pull requests in a day
 * produced more than a hundred CI runs, the morning's spin-up fell off the
 * first page, and the dashboard reported "unknown" for a server that was
 * running. Worse, the scheduled-teardown Worker fails closed on "unknown" and
 * skipped the teardown.
 *
 * So the caller says when it has seen enough, and this reads on until then.
 * It stops early in the common case — a lifecycle run on page one costs one
 * request, as before — and gives up after `maxPages`, or at the first empty
 * page, which is the end of the history.
 *
 * A failure on the first page is reported like listWorkflowRuns reports it,
 * and a thrown error there is thrown on. A failure on a later page is not a
 * failure of the call, whether it is an HTTP error, a timeout or an unreadable
 * body: the runs read so far are returned with `incomplete: true`, because a
 * partial list is still more than nothing and the caller already has to cope
 * with not finding what it looked for.
 *
 * `response` is the newest page that was read, so its rate-limit headers
 * reflect every request this call made.
 *
 * @param {object} env
 * @param {{ maxPages: number, enough: (runs: object[]) => boolean }} options
 * @returns {Promise<{ ok: true, runs: object[], response: Response, pages: number, incomplete?: true }
 *                  | { ok: false, response: Response }
 *                  | { ok: false, invalid: true, response: Response }>}
 */
export async function listWorkflowRunsUntil(env, { maxPages, enough }) {
  const { kind } = forgeConfig(env);
  const perPage = runsPageSize(env);
  const runs = [];
  // The newest page that was read. Its headers carry the rate-limit budget as
  // it stands after every request made here, which is what a caller that
  // paces itself by that budget needs to see.
  let latest = null;
  for (let page = 1; page <= maxPages; page += 1) {
    const query = kind === 'github' ? `?per_page=${perPage}&page=${page}` : `?page=${page}&limit=${perPage}`;
    const url = repoApiUrl(env, `/actions/runs${query}`);
    let response;
    let data;
    if (page === 1) {
      // The first page behaves exactly like listWorkflowRuns, thrown errors
      // included: with nothing read yet there is nothing to fall back on.
      response = await forgeFetch(env, url, { headers: forgeHeaders(env) });
      if (!response.ok) return { ok: false, response };
      data = await response.json();
      if (!data || !Array.isArray(data.workflow_runs)) return { ok: false, invalid: true, response };
    } else {
      // A later page that cannot be read — an HTTP error, a timeout, a body
      // that is not the expected JSON — ends the search with what there is.
      try {
        response = await forgeFetch(env, url, { headers: forgeHeaders(env) });
        data = response.ok ? await response.json() : null;
      } catch {
        data = null;
      }
      if (!data || !Array.isArray(data.workflow_runs)) {
        return { ok: true, runs, response: latest, pages: page - 1, incomplete: true };
      }
    }
    latest = response;
    const pageRuns = kind === 'github' ? data.workflow_runs : data.workflow_runs.map(normalizeForgejoRun);
    runs.push(...pageRuns);
    if (pageRuns.length === 0 || enough(runs)) return { ok: true, runs, response: latest, pages: page };
  }
  return { ok: true, runs, response: latest, pages: maxPages };
}
