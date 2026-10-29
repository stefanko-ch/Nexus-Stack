// A Control Plane whose repository lives on a Forgejo (a Nexus-Conductor
// fork) must call that forge, not api.github.com — where every call
// answered "Bad credentials" and no button worked.

import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import {
  dispatchWorkflow, forgeErrorMessage, forgeErrorStatus, listWorkflowRuns, normalizeForgejoRun,
} from '../functions/api/_utils/forge.js';

const GITHUB_ENV = { GITHUB_TOKEN: 'gh-token', GITHUB_OWNER: 'alice', GITHUB_REPO: 'stack' };
const FORGEJO_ENV = {
  ...GITHUB_ENV,
  GITHUB_OWNER: 'deads8',
  GITHUB_REPO: 'nexus-deads8-test',
  FORGE_URL: 'https://forgejo.example.com/',
  FORGE_ACCESS_CLIENT_ID: 'access-id',
  FORGE_ACCESS_CLIENT_SECRET: 'access-secret',
};

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

/** Records every request and answers each with `respond(url, init)`. */
function captureFetch(respond) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return respond(url, init);
  };
  return calls;
}

test('without FORGE_URL a dispatch goes to GitHub, as before', async () => {
  const calls = captureFetch(() => new Response(null, { status: 204 }));
  const response = await dispatchWorkflow(GITHUB_ENV, 'teardown.yml', { confirm: 'TEARDOWN' });

  assert.equal(response.status, 204);
  assert.equal(calls[0].url, 'https://api.github.com/repos/alice/stack/actions/workflows/teardown.yml/dispatches');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer gh-token');
  assert.equal(calls[0].init.headers['CF-Access-Client-Id'], undefined);
  assert.equal(calls[0].init.redirect, 'follow');
  assert.deepEqual(JSON.parse(calls[0].init.body), { ref: 'main', inputs: { confirm: 'TEARDOWN' } });
});

test('with FORGE_URL a dispatch goes to the forge, through Access', async () => {
  const calls = captureFetch(() => new Response(null, { status: 204 }));
  await dispatchWorkflow(FORGEJO_ENV, 'teardown.yml', { confirm: 'TEARDOWN' });

  assert.equal(
    calls[0].url,
    'https://forgejo.example.com/api/v1/repos/deads8/nexus-deads8-test/actions/workflows/teardown.yml/dispatches',
  );
  assert.equal(calls[0].init.headers.Authorization, 'token gh-token');
  assert.equal(calls[0].init.headers['CF-Access-Client-Id'], 'access-id');
  assert.equal(calls[0].init.headers['CF-Access-Client-Secret'], 'access-secret');
  // Access answers a refused token with a redirect to its login page;
  // following it would turn the failure into a 200 HTML page.
  assert.equal(calls[0].init.redirect, 'manual');
});

test('half an Access pair sends neither header', async () => {
  const calls = captureFetch(() => new Response(null, { status: 204 }));
  const { FORGE_ACCESS_CLIENT_SECRET, ...halfPair } = FORGEJO_ENV;
  await dispatchWorkflow(halfPair, 'spin-up.yml');

  assert.equal(calls[0].init.headers['CF-Access-Client-Id'], undefined);
  assert.equal(calls[0].init.headers['CF-Access-Client-Secret'], undefined);
});

test('a redirect is reported as Access refusing the token, and as a 502', async () => {
  const response = new Response(null, { status: 302, headers: { Location: 'https://x.cloudflareaccess.com/' } });

  assert.equal(forgeErrorStatus(response), 502);
  assert.match(await forgeErrorMessage(response, 'Failed to trigger workflow'), /Cloudflare Access/);
});

test('an error body is reduced to its message, never passed through raw', async () => {
  const json = new Response(JSON.stringify({ message: 'Bad credentials' }), { status: 401 });
  const html = new Response('<html>oops</html>', { status: 500 });

  assert.equal(await forgeErrorMessage(json, 'Failed'), 'Bad credentials');
  assert.equal(await forgeErrorMessage(html, 'Failed'), 'Failed: HTTP 500');
});

test("Forgejo's single status becomes GitHub's status and conclusion", () => {
  const base = { id: 7, workflow_id: 'spin-up.yml', created: '2026-10-29T14:00:00+01:00' };

  assert.deepEqual(
    [normalizeForgejoRun({ ...base, status: 'success' }).status, normalizeForgejoRun({ ...base, status: 'success' }).conclusion],
    ['completed', 'success'],
  );
  assert.equal(normalizeForgejoRun({ ...base, status: 'failure' }).conclusion, 'failure');
  assert.equal(normalizeForgejoRun({ ...base, status: 'running' }).status, 'in_progress');
  // Waiting on the infrastructure concurrency group is not completed.
  assert.equal(normalizeForgejoRun({ ...base, status: 'blocked' }).status, 'queued');
  assert.equal(normalizeForgejoRun({ ...base, status: 'waiting' }).conclusion, null);
});

test('a Forgejo run gets a path from its workflow file and UTC timestamps', () => {
  const run = normalizeForgejoRun({
    id: 7,
    status: 'success',
    workflow_id: 'teardown-snapshot.yml',
    title: 'fix: Setup something',
    created: '2026-10-29T14:00:00+01:00',
    updated: '2026-10-29T14:10:00+01:00',
    started: '1970-01-01T01:00:00+01:00',
  });

  assert.equal(run.path, '.github/workflows/teardown-snapshot.yml');
  // Never the title: a commit subject containing "Setup" would match the
  // endpoints' name-based fallback and be counted as a setup run.
  assert.equal(run.name, '');
  assert.equal(run.created_at, '2026-10-29T13:00:00.000Z');
  assert.equal(run.updated_at, '2026-10-29T13:10:00.000Z');
  // An unset `started` is the epoch; the queue time stands in.
  assert.equal(run.run_started_at, '2026-10-29T13:00:00.000Z');
});

test('the run list uses page + limit on Forgejo and normalises every run', async () => {
  const calls = captureFetch(() => new Response(JSON.stringify({
    workflow_runs: [{ id: 2, status: 'running', workflow_id: 'spin-up.yml', created: '2026-10-29T13:00:00Z' }],
    total_count: 1,
  }), { status: 200 }));
  const listed = await listWorkflowRuns(FORGEJO_ENV, 100);

  assert.equal(calls[0].url, 'https://forgejo.example.com/api/v1/repos/deads8/nexus-deads8-test/actions/runs?page=1&limit=100');
  assert.equal(listed.ok, true);
  assert.equal(listed.runs[0].status, 'in_progress');
  assert.equal(listed.runs[0].path, '.github/workflows/spin-up.yml');
});

test('the run list on GitHub is passed through unchanged', async () => {
  const run = { id: 1, status: 'completed', conclusion: 'success', path: '.github/workflows/spin-up.yml', name: 'Spin Up' };
  const calls = captureFetch(() => new Response(JSON.stringify({ workflow_runs: [run] }), { status: 200 }));
  const listed = await listWorkflowRuns(GITHUB_ENV, 20);

  assert.equal(calls[0].url, 'https://api.github.com/repos/alice/stack/actions/runs?per_page=20');
  assert.deepEqual(listed.runs, [run]);
});

test('a run list without workflow_runs is invalid, not empty', async () => {
  captureFetch(() => new Response(JSON.stringify({ message: 'nope' }), { status: 200 }));
  const listed = await listWorkflowRuns(FORGEJO_ENV, 20);

  assert.equal(listed.ok, false);
  assert.equal(listed.invalid, true);
});
