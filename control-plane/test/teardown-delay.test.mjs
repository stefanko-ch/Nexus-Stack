// A delayed teardown runs when the delay ends.
//
// "Delay Teardown by 4 Hours" used to skip the night's teardown outright. The
// teardown trigger fires once a day; it found the delay in force and returned,
// and nothing fired again when the delay ran out. The Settings page said
// "Teardown delayed until 01:47" while the server ran until the next evening.
//
// The Worker now records that a teardown is owed, and a frequent "delay check"
// trigger pays it once the delay is over. These tests drive the Worker through
// scheduled() with a D1 stand-in and a forge stand-in.

import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import worker from '../worker/src/index.js';

const NOTIFICATION_CRON = '45 20 * * *';
const TEARDOWN_CRON = '0 21 * * *';
const DELAY_CHECK_CRON = '*/15 * * * *';
const OWED = 'teardown_owed_after_delay';

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

const hoursFromNow = (h) => new Date(Date.now() + h * 3600 * 1000).toISOString();

const run = (file, name, overrides = {}) => ({
  id: 1, status: 'completed', conclusion: 'success', name,
  path: `.github/workflows/${file}`,
  created_at: '2026-11-10T10:27:00Z', updated_at: '2026-11-10T10:40:00Z',
  ...overrides,
});
const DEPLOYED = [run('spin-up.yml', 'Spin Up')];
const TORN_DOWN = [run('teardown.yml', 'Teardown')];
const SPINNING_UP = [run('spin-up.yml', 'Spin Up', { status: 'in_progress', conclusion: null })];

/** A D1 stand-in whose config table can be read, written and deleted from. */
function fakeD1(initial = {}) {
  const config = { lifecycle_mode: 'rebuild', ...initial };
  const logs = [];
  return {
    config,
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
          else if (sql.startsWith('INSERT INTO config')) config[bound[0]] = bound[1];
          else if (sql.startsWith('DELETE FROM config')) delete config[bound[0]];
          return { success: true, meta: { changes: 0 } };
        },
      };
      return statement;
    },
  };
}

/** A forge stand-in: serves `runs` as the run list and records teardown dispatches. */
function forge(runs, { listStatus = 200, dispatchStatus = 204 } = {}) {
  const dispatched = [];
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input instanceof Request ? input.url : input);
    if (url.includes('/dispatches')) {
      dispatched.push({ url, body: JSON.parse(init.body) });
      if (dispatchStatus !== 204) return new Response('nope', { status: dispatchStatus });
      return new Response(null, { status: 204 });
    }
    if (url.includes('/actions/runs?')) {
      if (listStatus !== 200) return new Response('boom', { status: listStatus });
      const page = Number(new URL(url).searchParams.get('page') ?? '1');
      return new Response(JSON.stringify({ workflow_runs: page === 1 ? runs : [] }), { status: 200 });
    }
    throw new Error(`unexpected request in test: ${url}`);
  };
  return dispatched;
}

async function fire(cron, { config = {}, runs = DEPLOYED, listStatus = 200, dispatchStatus = 204 } = {}) {
  const dispatched = forge(runs, { listStatus, dispatchStatus });
  const db = fakeD1(config);
  const pending = [];
  await worker.scheduled(
    { cron },
    {
      GITHUB_TOKEN: 'gh-token', GITHUB_OWNER: 'alice', GITHUB_REPO: 'stack', DOMAIN: 'example.com',
      NOTIFICATION_CRON, TEARDOWN_CRON, DELAY_CHECK_CRON, NEXUS_DB: db,
    },
    { waitUntil: (p) => pending.push(p) },
  );
  await Promise.all(pending);
  return { dispatched, config: db.config, messages: db.logs.map((l) => l.message) };
}

// ---- the nightly trigger -----------------------------------------------------

test('the nightly teardown stands down for a delay and records that a teardown is owed', async () => {
  const { dispatched, config } = await fire(TEARDOWN_CRON, { config: { delay_until: hoursFromNow(3) } });
  assert.equal(dispatched.length, 0);
  assert.ok(config[OWED], 'the owed marker is set');
  assert.ok(config.delay_until, 'the delay stays');
});

test('the notification trigger standing down for a delay owes no teardown', async () => {
  const { dispatched, config } = await fire(NOTIFICATION_CRON, { config: { delay_until: hoursFromNow(3) } });
  assert.equal(dispatched.length, 0);
  assert.equal(config[OWED], undefined);
});

test('the nightly teardown without a delay runs and clears a stale owed marker', async () => {
  const { dispatched, config } = await fire(TEARDOWN_CRON, { config: { [OWED]: hoursFromNow(-30) } });
  assert.equal(dispatched.length, 1);
  assert.match(dispatched[0].url, /\/actions\/workflows\/teardown\.yml\/dispatches$/);
  assert.deepEqual(dispatched[0].body.inputs, { confirm: 'TEARDOWN' });
  assert.equal(config[OWED], undefined);
});

// ---- the delay check ---------------------------------------------------------

test('delay check: while the delay is in force nothing happens and the teardown stays owed', async () => {
  const { dispatched, config, messages } = await fire(DELAY_CHECK_CRON, {
    config: { delay_until: hoursFromNow(1), [OWED]: hoursFromNow(-2) },
  });
  assert.equal(dispatched.length, 0);
  assert.ok(config[OWED]);
  assert.deepEqual(messages, [], 'a quiet check writes no log rows');
});

test('delay check: once the delay has ended the postponed teardown is dispatched', async () => {
  const { dispatched, config, messages } = await fire(DELAY_CHECK_CRON, {
    config: { delay_until: hoursFromNow(-0.1), [OWED]: hoursFromNow(-4) },
  });
  assert.equal(dispatched.length, 1);
  assert.match(dispatched[0].url, /\/actions\/workflows\/teardown\.yml\/dispatches$/);
  assert.equal(config[OWED], undefined, 'the debt is paid');
  assert.equal(config.delay_until, undefined, 'the spent delay is cleared');
  assert.ok(messages.some((m) => /postponed teardown/.test(m)), messages.join(' | '));
});

test('delay check: on the snapshot lifecycle the snapshot teardown is dispatched', async () => {
  const { dispatched } = await fire(DELAY_CHECK_CRON, {
    config: { lifecycle_mode: 'snapshot', delay_until: hoursFromNow(-0.1), [OWED]: hoursFromNow(-4) },
  });
  assert.equal(dispatched.length, 1);
  assert.match(dispatched[0].url, /\/actions\/workflows\/teardown-snapshot\.yml\/dispatches$/);
});

test('delay check: a delay that ended before the nightly teardown owes nothing', async () => {
  // Delayed at 15:00 by four hours: over at 19:00, two hours before the
  // nightly run. Tearing down at 19:00 would be earlier than the schedule.
  const { dispatched, messages } = await fire(DELAY_CHECK_CRON, { config: { delay_until: hoursFromNow(-0.1) } });
  assert.equal(dispatched.length, 0);
  assert.deepEqual(messages, []);
});

test('delay check: with nothing owed and no delay it does nothing and logs nothing', async () => {
  const { dispatched, messages } = await fire(DELAY_CHECK_CRON);
  assert.equal(dispatched.length, 0);
  assert.deepEqual(messages, []);
});

test('delay check: a stack that was torn down by hand in the meantime is left alone', async () => {
  const { dispatched, config } = await fire(DELAY_CHECK_CRON, {
    config: { delay_until: hoursFromNow(-0.1), [OWED]: hoursFromNow(-4) },
    runs: TORN_DOWN,
  });
  assert.equal(dispatched.length, 0);
  assert.equal(config[OWED], undefined, 'nothing is owed for a stack that is already down');
});

test('delay check: when the state cannot be determined the teardown stays owed for the next check', async () => {
  const { dispatched, config, messages } = await fire(DELAY_CHECK_CRON, {
    config: { delay_until: hoursFromNow(-0.1), [OWED]: hoursFromNow(-4) },
    listStatus: 502,
  });
  assert.equal(dispatched.length, 0);
  assert.ok(config[OWED], 'fail closed, but do not forget');
  assert.ok(messages.some((m) => /could not be determined/.test(m)), messages.join(' | '));
});

test('delay check: when the forge refuses the dispatch the teardown stays owed', async () => {
  const { dispatched, config } = await fire(DELAY_CHECK_CRON, {
    config: { delay_until: hoursFromNow(-0.1), [OWED]: hoursFromNow(-4) },
    dispatchStatus: 503,
  });
  assert.equal(dispatched.length, 1, 'it tried');
  assert.ok(config[OWED], 'a failed dispatch is not a paid debt');
  assert.ok(config.delay_until, 'and the delay record is kept with it');
});

test('delay check: while a lifecycle run is in flight it waits', async () => {
  const { dispatched, config } = await fire(DELAY_CHECK_CRON, {
    config: { delay_until: hoursFromNow(-0.1), [OWED]: hoursFromNow(-4) },
    runs: SPINNING_UP,
  });
  assert.equal(dispatched.length, 0);
  assert.ok(config[OWED]);
});

test('delay check: with scheduled teardown switched off the debt is dropped', async () => {
  const { dispatched, config } = await fire(DELAY_CHECK_CRON, {
    config: { teardown_enabled: 'false', [OWED]: hoursFromNow(-4) },
  });
  assert.equal(dispatched.length, 0);
  assert.equal(config[OWED], undefined);
});

test('a second delay moves the postponed teardown with it', async () => {
  // Owed since the nightly run, then delayed again: the check waits for the new end.
  const waiting = await fire(DELAY_CHECK_CRON, { config: { delay_until: hoursFromNow(2), [OWED]: hoursFromNow(-3) } });
  assert.equal(waiting.dispatched.length, 0);
  const due = await fire(DELAY_CHECK_CRON, { config: { delay_until: hoursFromNow(-0.01), [OWED]: hoursFromNow(-5) } });
  assert.equal(due.dispatched.length, 1);
});
