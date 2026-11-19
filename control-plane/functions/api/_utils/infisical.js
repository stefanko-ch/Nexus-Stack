/**
 * Shared Infisical fetch helper.
 *
 * Fetches every secret of the project in ONE request and groups it by folder.
 * Consumed by:
 *   - GET /api/secrets          (renders the Secrets page)
 *   - POST /api/databricks-sync (pushes the same inventory into Databricks)
 *
 * Keeping both endpoints on one code path guarantees the UI and the Databricks
 * scope stay in lockstep — whatever you see on /secrets is exactly what a
 * sync will upsert.
 *
 * ONE REQUEST, on purpose (#1036). This used to list the folders and then
 * fetch each folder separately, all inside one Pages Function invocation.
 * A Pages Function may make at most 50 subrequests per invocation on the
 * Workers free plan, and the bootstrap pushes over a hundred folders, so
 * every folder past roughly the 50th failed. Each failure became a warning
 * the Secrets page never showed, and the list simply ended at `mage`. Worse,
 * the Databricks sync deletes scope keys it does not see in the inventory,
 * so a truncated inventory deleted the keys of every folder past the cap.
 *
 * `GET /api/v3/secrets/raw?secretPath=/&recursive=true` returns every secret
 * below the root, each with the `secretPath` of its folder. Checked in the
 * pinned Infisical v0.155.5: the route accepts `recursive`
 * (backend/src/server/routes/v3/deprecated-secret-router.ts) and its
 * response schema carries `secretPath`. The result is all or nothing: this
 * helper returns the whole inventory or throws, never a partial one.
 */
import { fetchWithTimeout } from './fetch-with-timeout.js';
import { safeHttpsUrl } from './url.js';

async function safeJsonParse(response, label) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const bodyPreview = (await response.text()).substring(0, 200);
    throw new Error(
      `${label} returned non-JSON response (${response.status}, content-type: ${contentType}). ` +
      `This usually means Cloudflare Access is blocking the request. Preview: ${bodyPreview}`
    );
  }
  return response.json();
}

/** The group a secret belongs to: its folder path without the leading slash, or `root`. */
export function groupNameForPath(secretPath) {
  const trimmed = (secretPath || '/').replace(/^\/+|\/+$/g, '');
  return trimmed === '' ? 'root' : trimmed;
}

/**
 * Group a recursive secrets listing by folder, dropping empty values.
 *
 * @param {Array<{ secretKey: string, secretValue?: string, secretPath?: string }>} secrets
 * @returns {Array<{ name: string, secrets: Array<{ key: string, value: string }> }>}
 */
export function groupSecrets(secrets) {
  const byGroup = new Map();
  for (const s of secrets || []) {
    if (s.secretValue === undefined || s.secretValue === '') continue;
    const name = groupNameForPath(s.secretPath);
    if (!byGroup.has(name)) byGroup.set(name, []);
    byGroup.get(name).push({ key: s.secretKey, value: s.secretValue });
  }
  return [...byGroup.entries()]
    .map(([name, list]) => ({ name, secrets: list.sort((a, b) => a.key.localeCompare(b.key)) }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Fetch every secret from the Infisical project.
 *
 * @param {object} env - Pages Function env bindings
 * @returns {Promise<{
 *   configured: boolean,
 *   groups: Array<{ name: string, secrets: Array<{ key: string, value: string }> }>,
 *   warnings: string[],
 *   message?: string,
 * }>}
 *
 * When Infisical env vars are missing, returns `{ configured: false, groups: [], warnings: [], message }`
 * rather than throwing, matching the prior /api/secrets behaviour.
 *
 * Any failure of the one request throws; the caller catches and surfaces it.
 * `warnings` is always empty and stays in the shape for the callers.
 */
export async function fetchAllInfisicalSecrets(env) {
  const token = env.INFISICAL_TOKEN;
  const projectId = env.INFISICAL_PROJECT_ID;
  const domain = env.DOMAIN;

  if (!token || !projectId || !domain) {
    return {
      configured: false,
      groups: [],
      warnings: [],
      message: 'Infisical not configured. Ensure INFISICAL_TOKEN, INFISICAL_PROJECT_ID, and DOMAIN are set.',
    };
  }

  const baseUrl = safeHttpsUrl(env.INFISICAL_URL, `https://infisical.${domain}`);
  if (!baseUrl) {
    // safeHttpsUrl returns '' if both candidate and fallback fail to parse as
    // https URLs. Without this guard, fetches below would resolve as relative
    // paths against the Control Plane origin and leak the Infisical bearer
    // token to the wrong host.
    return {
      configured: false,
      groups: [],
      warnings: [],
      message: `Infisical misconfigured: INFISICAL_URL is invalid and fallback https://infisical.${domain} did not parse as https.`,
    };
  }
  const environment = env.INFISICAL_ENV || 'dev';
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // Cloudflare Access service-token headers for machine-to-machine auth
  const cfAccessClientId = env.CF_ACCESS_CLIENT_ID;
  const cfAccessClientSecret = env.CF_ACCESS_CLIENT_SECRET;
  if (cfAccessClientId && cfAccessClientSecret) {
    headers['CF-Access-Client-Id'] = cfAccessClientId;
    headers['CF-Access-Client-Secret'] = cfAccessClientSecret;
  }

  // One subrequest for the whole project; see the header for why.
  const res = await fetchWithTimeout(
    `${baseUrl}/api/v3/secrets/raw?workspaceId=${projectId}&environment=${environment}&secretPath=/&recursive=true`,
    { headers }
  );

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to fetch secrets from Infisical (${res.status}): ${errText.substring(0, 200)}`);
  }

  const data = await safeJsonParse(res, 'Secrets API');
  return { configured: true, groups: groupSecrets(data.secrets), warnings: [] };
}
