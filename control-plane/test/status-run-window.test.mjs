// The infrastructure state must not depend on how much CI ran since the last
// lifecycle run.
//
// Both the dashboard (GET /api/status) and the scheduled-teardown Worker used
// to read one page of the repository's workflow runs and look for a lifecycle
// run in it. The page holds every workflow's runs. On a day with a dozen
// merged pull requests, more than a hundred CI runs followed the morning's
// spin-up, the spin-up fell off the page, and both reported "unknown" for a
// server that was running. The Worker fails closed on "unknown", so it also
// skipped the scheduled teardown.
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import { onRequestGet as getStatus } from '../functions/api/status.js';
import { onRequestGet as getInfo } from '../functions/api/info.js';
import { _resetJwksCache } from '../functions/api/_utils/access-jwt.js';
import { listWorkflowRunsUntil, runsPageSize } from '../functions/api/_utils/forge.js';
import worker from '../worker/src/index.js';
import { makeKeypair, signToken, requestWithToken } from './helpers.mjs';

const GITHUB_ENV = { GITHUB_TOKEN: 'gh-token', GITHUB_OWNER: 'alice', GITHUB_REPO: 'stack' };
const FORGEJO_ENV = { ...GITHUB_ENV, FORGE_URL: 'https://forgejo.example.com' };

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  _resetJwksCache();
});

let nextId = 1;
const ciRun = () => ({
  id: nextId++, status: 'completed', conclusion: 'success', name: 'CI: Python Tests',
  path: '.github/workflows/python-tests.yml',
  created_at: '2026-11-10T12:00:00Z', updated_at: '2026-11-10T12:05:00Z',
});
const lifecycleRun = (file, name, overrides = {}) => ({
  id: nextId++, status: 'completed', conclusion: 'success', name,
  path: `.github/workflows/${file}`,
  created_at: '2026-11-10T10:27:00Z', updated_at: '2026-11-10T10:40:00Z',
  ...overrides,
});
const pageOfCi = (n) => Array.from({ length: n }, ciRun);

/**
 * A fetch stand-in for the forge: `pages[i]` is page i+1 of the run list, and
 * anything past the end is empty. Also serves the Access JWKS when given one.
 * Records the run-list URLs it was asked for.
 */
function forgeFetch(pages, { jwks = null, failFrom = null, throwFrom = null, remaining = null } = {}) {
  const asked = [];
  globalThis.fetch = async (input) => {
    const url = String(input instanceof Request ? input.url : input);
    if (url.includes('/cdn-cgi/access/certs')) {
      return new Response(JSON.stringify({ keys: jwks }), { status: 200 });
    }
    if (url.includes('/actions/runs?')) {
      asked.push(url);
      const page = Number(new URL(url).searchParams.get('page') ?? '1');
      if (throwFrom !== null && page >= throwFrom) throw new Error('network down');
      if (failFrom !== null && page >= failFrom) return new Response('boom', { status: 502 });
      const headers = remaining ? { 'x-ratelimit-remaining': String(remaining - page) } : {};
      return new Response(JSON.stringify({ workflow_runs: pages[page - 1] ?? [] }), { status: 200, headers });
    }
    throw new Error(`unexpected request in test: ${url}`);
  };
  return asked;
}

// ---- the paging helper ------------------------------------------------------

test('one request when the first page already answers', async () => {
  const asked = forgeFetch([[ciRun(), lifecycleRun('spin-up.yml', 'Spin Up')], pageOfCi(100)]);
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, {
    maxPages: 10,
    enough: (runs) => runs.some((r) => r.path.includes('spin-up.yml')),
  });
  assert.equal(asked.length, 1);
  assert.equal(asked[0], 'https://api.github.com/repos/alice/stack/actions/runs?per_page=100&page=1');
  assert.equal(listed.ok, true);
  assert.equal(listed.pages, 1);
  assert.equal(listed.runs.length, 2);
});

test('it reads on, page by page, until the caller has enough', async () => {
  const asked = forgeFetch([pageOfCi(100), pageOfCi(100), [lifecycleRun('spin-up.yml', 'Spin Up')]]);
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, {
    maxPages: 10,
    enough: (runs) => runs.some((r) => r.path.includes('spin-up.yml')),
  });
  assert.deepEqual(asked.map((u) => new URL(u).searchParams.get('page')), ['1', '2', '3']);
  assert.equal(listed.pages, 3);
  assert.equal(listed.runs.length, 201);
});

test('it stops at maxPages when the caller never has enough', async () => {
  const asked = forgeFetch([pageOfCi(100), pageOfCi(100), pageOfCi(100), pageOfCi(100)]);
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, { maxPages: 3, enough: () => false });
  assert.equal(asked.length, 3);
  assert.equal(listed.ok, true);
  assert.equal(listed.runs.length, 300);
});

test('an empty page is the end of the history', async () => {
  const asked = forgeFetch([pageOfCi(100)]);
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, { maxPages: 10, enough: () => false });
  assert.equal(asked.length, 2);
  assert.equal(listed.runs.length, 100);
  assert.equal(listed.incomplete, undefined);
});

test('a failure on the first page is a failure', async () => {
  forgeFetch([], { failFrom: 1 });
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, { maxPages: 10, enough: () => false });
  assert.equal(listed.ok, false);
  assert.equal(listed.response.status, 502);
});

test('a failure on a later page keeps what was read and says it is incomplete', async () => {
  forgeFetch([pageOfCi(100)], { failFrom: 2 });
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, { maxPages: 10, enough: () => false });
  assert.equal(listed.ok, true);
  assert.equal(listed.incomplete, true);
  assert.equal(listed.runs.length, 100);
  assert.equal(listed.pages, 1);
});

test('a thrown error on a later page also keeps what was read', async () => {
  forgeFetch([pageOfCi(100)], { throwFrom: 2 });
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, { maxPages: 10, enough: () => false });
  assert.equal(listed.ok, true);
  assert.equal(listed.incomplete, true);
  assert.equal(listed.runs.length, 100);
});

test('a thrown error on the first page is thrown on, as listWorkflowRuns does', async () => {
  forgeFetch([], { throwFrom: 1 });
  await assert.rejects(
    listWorkflowRunsUntil(GITHUB_ENV, { maxPages: 10, enough: () => false }),
    /network down/,
  );
});

test('the response returned is the newest page read, so its rate-limit header is current', async () => {
  forgeFetch([pageOfCi(100), pageOfCi(100), [lifecycleRun('spin-up.yml', 'Spin Up')]], { remaining: 5000 });
  const listed = await listWorkflowRunsUntil(GITHUB_ENV, {
    maxPages: 10,
    enough: (runs) => runs.some((r) => r.path.includes('spin-up.yml')),
  });
  assert.equal(listed.response.headers.get('x-ratelimit-remaining'), '4997');
});

test('Forgejo pages are fifty runs, asked for with page and limit', async () => {
  const asked = forgeFetch([[], []]);
  await listWorkflowRunsUntil(FORGEJO_ENV, { maxPages: 2, enough: () => false });
  assert.equal(runsPageSize(FORGEJO_ENV), 50);
  assert.equal(runsPageSize(GITHUB_ENV), 100);
  assert.equal(asked[0], 'https://forgejo.example.com/api/v1/repos/alice/stack/actions/runs?page=1&limit=50');
});

// ---- GET /api/status --------------------------------------------------------

const STATUS_ENV = { ...GITHUB_ENV, ACCESS_TEAM_DOMAIN: 'testteam', ACCESS_AUD: 'test-aud' };

async function status(pages, options = {}) {
  const { privateKey, jwk, kid } = await makeKeypair();
  const asked = forgeFetch(pages, { ...options, jwks: [jwk] });
  _resetJwksCache();
  const token = await signToken({ privateKey, kid, payload: { email: 'someone@example.com' } });
  const response = await getStatus({
    env: STATUS_ENV,
    request: requestWithToken(token, 'https://control.example.com/api/status'),
  });
  return { response, body: JSON.parse(await response.text()), asked };
}

test('status: the rate-limit budget reported is the one left after the last page', async () => {
  const { body } = await status([pageOfCi(100), [lifecycleRun('spin-up.yml', 'Spin Up')]], { remaining: 5000 });
  assert.equal(body.rateLimitRemaining, 4998);
});

test('status: a later page that cannot be read leaves the state unknown, not the endpoint broken', async () => {
  const { response, body } = await status([pageOfCi(100)], { throwFrom: 2 });
  assert.equal(response.status, 200);
  assert.equal(body.infraState, 'unknown');
});

test('status: a spin-up behind a full page of CI runs still reads as deployed', async () => {
  const { response, body, asked } = await status([pageOfCi(100), [lifecycleRun('spin-up.yml', 'Spin Up')]]);
  assert.equal(response.status, 200);
  assert.equal(body.infraState, 'deployed');
  assert.equal(asked.length, 2);
  assert.equal(body.workflows.spinUp.conclusion, 'success');
});

test('status: a teardown behind two pages of CI runs still reads as torn down', async () => {
  const { body } = await status([
    pageOfCi(100), pageOfCi(100),
    [lifecycleRun('teardown-snapshot.yml', 'Teardown'), lifecycleRun('spin-up-snapshot.yml', 'Spin Up', { updated_at: '2026-11-09T08:00:00Z' })],
  ]);
  assert.equal(body.infraState, 'torn-down');
});

test('status: a failed spin-up does not end the search; the teardown before it decides', async () => {
  const { body } = await status([
    [...pageOfCi(99), lifecycleRun('spin-up.yml', 'Spin Up', { conclusion: 'failure' })],
    [lifecycleRun('teardown.yml', 'Teardown', { updated_at: '2026-11-09T21:40:00Z' })],
  ]);
  assert.equal(body.infraState, 'torn-down');
});

test('status: a lifecycle run on the first page costs one request, as before', async () => {
  const { body, asked } = await status([[ciRun(), lifecycleRun('spin-up.yml', 'Spin Up')], pageOfCi(100)]);
  assert.equal(body.infraState, 'deployed');
  assert.equal(asked.length, 1);
});

test('status: a repository with no lifecycle run at all is still unknown', async () => {
  const { body } = await status([pageOfCi(100), pageOfCi(40)]);
  assert.equal(body.infraState, 'unknown');
});

test('status: a run still in progress is reported from the first page', async () => {
  const { body, asked } = await status([
    [lifecycleRun('teardown.yml', 'Teardown', { status: 'in_progress', conclusion: null }), ...pageOfCi(99)],
  ]);
  assert.equal(body.infraState, 'running');
  assert.equal(body.inProgress, true);
  // One request for the run list; the step list is a different URL.
  assert.equal(asked.length, 1);
});

// ---- the scheduled-teardown Worker ------------------------------------------

/** A D1 stand-in: answers config lookups from `config` and records log inserts. */
function fakeD1(config = {}) {
  const logs = [];
  return {
    logs,
    prepare(sql) {
      let bound = [];
      const statement = {
        bind(...args) { bound = args; return statement; },
        async first() {
          if (sql.includes('FROM config')) return bound[0] in config ? { value: config[bound[0]] } : null;
          return null;
        },
        async all() { return { results: [] }; },
        async run() {
          if (sql.startsWith('INSERT INTO logs')) logs.push({ level: bound[1], message: bound[2] });
          return { success: true };
        },
      };
      return statement;
    },
  };
}

async function runWorker(pages, env = {}, options = {}) {
  const asked = forgeFetch(pages, options);
  const db = fakeD1();
  const pending = [];
  await worker.scheduled(
    // A cron that is neither the notification nor the teardown trigger, so the
    // run stops after deciding the state and nothing is dispatched or mailed.
    { cron: '1 2 3 4 5' },
    { ...GITHUB_ENV, DOMAIN: 'example.com', NEXUS_DB: db, ...env },
    { waitUntil: (p) => pending.push(p) },
  );
  await Promise.all(pending);
  return { messages: db.logs.map((l) => l.message), asked };
}

const UNDETERMINED = /Could not determine infrastructure state/;
const NOT_DEPLOYED = /Infrastructure is not deployed/;

test('worker: a spin-up behind a full page of CI runs does not stop the scheduled teardown', async () => {
  const { messages, asked } = await runWorker([pageOfCi(100), [lifecycleRun('spin-up.yml', 'Spin Up')]]);
  assert.ok(!messages.some((m) => UNDETERMINED.test(m)), `the worker gave up: ${messages.join(' | ')}`);
  assert.ok(!messages.some((m) => NOT_DEPLOYED.test(m)));
  assert.equal(asked.length, 2);
});

test('worker: a teardown behind a full page of CI runs is recognised as torn down', async () => {
  const { messages } = await runWorker([pageOfCi(100), [lifecycleRun('teardown.yml', 'Teardown')]]);
  assert.ok(messages.some((m) => NOT_DEPLOYED.test(m) && m.includes('torn-down')), messages.join(' | '));
});

test('worker: with no lifecycle run anywhere it still fails closed', async () => {
  const { messages } = await runWorker([pageOfCi(100), pageOfCi(10)]);
  assert.ok(messages.some((m) => UNDETERMINED.test(m)), messages.join(' | '));
});

test('worker: on Forgejo it pages fifty at a time', async () => {
  const { messages, asked } = await runWorker(
    [pageOfCi(50).map((r) => ({ id: r.id, status: 'success', workflow_id: 'python-tests.yml', created: '2026-11-10T12:00:00Z' })),
      [{ id: 9001, status: 'success', workflow_id: 'spin-up.yml', created: '2026-11-10T10:27:00Z', stopped: '2026-11-10T10:40:00Z' }]],
    { FORGE_URL: 'https://forgejo.example.com' },
  );
  assert.ok(!messages.some((m) => UNDETERMINED.test(m)), messages.join(' | '));
  assert.equal(asked[0], 'https://forgejo.example.com/api/v1/repos/alice/stack/actions/runs?page=1&limit=50');
  assert.equal(asked.length, 2);
});

// The safety property: the Worker never decides on a list it could not read to
// the end. A later page that fails must not be read as "no lifecycle run", and
// certainly not as a state.
test('worker: a later page that answers with an error fails closed', async () => {
  const { messages, asked } = await runWorker([pageOfCi(100)], {}, { failFrom: 2 });
  assert.ok(messages.some((m) => UNDETERMINED.test(m)), messages.join(' | '));
  assert.equal(asked.length, 2, 'it stops at the page that failed');
});

test('worker: a later page that cannot be reached fails closed', async () => {
  const { messages } = await runWorker([pageOfCi(100)], {}, { throwFrom: 2 });
  assert.ok(messages.some((m) => UNDETERMINED.test(m)), messages.join(' | '));
});

// ---- GET /api/info ----------------------------------------------------------

async function info(pages) {
  const { privateKey, jwk, kid } = await makeKeypair();
  const asked = forgeFetch(pages, { jwks: [jwk] });
  _resetJwksCache();
  const token = await signToken({ privateKey, kid, payload: { email: 'someone@example.com' } });
  const response = await getInfo({
    env: STATUS_ENV,
    request: requestWithToken(token, 'https://control.example.com/api/info'),
  });
  return { response, body: JSON.parse(await response.text()), asked };
}

test('info: the last deploy is found behind a full page of CI runs', async () => {
  const { response, body, asked } = await info([pageOfCi(100), [lifecycleRun('spin-up.yml', 'Spin Up')]]);
  assert.equal(response.status, 200);
  assert.equal(body.info.time.lastDeploy, '2026-11-10T10:40:00Z');
  assert.equal(asked.length, 2);
});

test('info: a failed spin-up is not the last deploy; the search reads on to the successful one', async () => {
  const { body, asked } = await info([
    [...pageOfCi(99), lifecycleRun('spin-up.yml', 'Spin Up', { conclusion: 'failure', updated_at: '2026-11-10T11:00:00Z' })],
    [lifecycleRun('spin-up-snapshot.yml', 'Lifecycle: Spin Up (Snapshot)')],
  ]);
  assert.equal(body.info.time.lastDeploy, '2026-11-10T10:40:00Z');
  assert.equal(asked.length, 2);
});
