// Whether a stack's owner gets its notification mails is that person's
// own choice, so the user role may change it — the admin alone could
// before, and a student who wanted the mails off (or on) had no way to.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { onRequestGet, onRequestPost } from '../functions/api/email-settings.js';
import { _resetJwksCache } from '../functions/api/_utils/access-jwt.js';
import { makeKeypair, signToken, jwksFetch } from './helpers.mjs';

const ORIGIN = 'https://control.example.com';

/** A D1 stand-in for the `config` table. */
function fakeDb() {
  const rows = new Map();
  return {
    rows,
    prepare(sql) {
      return {
        bind(...args) {
          return {
            async first() {
              return rows.has(args[0]) ? { value: rows.get(args[0]) } : null;
            },
            async run() {
              if (/INSERT OR REPLACE INTO config/.test(sql)) rows.set(args[0], args[1]);
              return {};
            },
          };
        },
        async run() { return {}; },
      };
    },
  };
}

const ENV = {
  ADMIN_EMAIL: 'admin@example.com',
  USER_EMAIL: 'student@example.com',
  ACCESS_TEAM_DOMAIN: 'testteam',
  ACCESS_AUD: 'test-aud',
};

async function get(email, db) {
  const { privateKey, jwk, kid } = await makeKeypair();
  const original = globalThis.fetch;
  globalThis.fetch = jwksFetch([jwk]);
  _resetJwksCache();
  try {
    const token = await signToken({ privateKey, kid, payload: { email } });
    const request = new Request(`${ORIGIN}/api/email-settings`, {
      headers: { 'Cf-Access-Jwt-Assertion': token },
    });
    return await onRequestGet({ env: { ...ENV, NEXUS_DB: db }, request });
  } finally {
    globalThis.fetch = original;
    _resetJwksCache();
  }
}

async function post(email, payload, db) {
  const { privateKey, jwk, kid } = await makeKeypair();
  const original = globalThis.fetch;
  globalThis.fetch = jwksFetch([jwk]);
  _resetJwksCache();
  try {
    const token = await signToken({ privateKey, kid, payload: { email } });
    const request = new Request(`${ORIGIN}/api/email-settings`, {
      method: 'POST',
      headers: {
        'Cf-Access-Jwt-Assertion': token,
        'Content-Type': 'application/json',
        Origin: ORIGIN,
      },
      body: JSON.stringify(payload),
    });
    const env = {
      ADMIN_EMAIL: 'admin@example.com',
      USER_EMAIL: 'student@example.com',
      ACCESS_TEAM_DOMAIN: 'testteam',
      ACCESS_AUD: 'test-aud',
      NEXUS_DB: db,
    };
    return await onRequestPost({ env, request });
  } finally {
    globalThis.fetch = original;
    _resetJwksCache();
  }
}

test("the stack's user can turn the stack-online mail on, which clears silent mode", async () => {
  const db = fakeDb();
  db.rows.set('silent_mode', 'true');

  const response = await post('student@example.com', { notifyOnSpinup: true }, db);

  assert.equal(response.status, 200);
  assert.equal(db.rows.get('notify_on_spinup'), 'true');
  assert.equal(db.rows.get('silent_mode'), 'false');
});

test("the stack's user can turn the mails off", async () => {
  const db = fakeDb();

  const response = await post('student@example.com', { notifyOnShutdown: false }, db);

  assert.equal(response.status, 200);
  assert.equal(db.rows.get('notify_on_shutdown'), 'false');
});

test('a guest still cannot change them', async () => {
  const db = fakeDb();

  const response = await post('guest@example.com', { notifyOnSpinup: false }, db);

  assert.equal(response.status, 403);
  assert.equal(db.rows.size, 0);
});

test("the stack's user can read the settings the page shows", async () => {
  const db = fakeDb();
  db.rows.set('notify_on_spinup', 'false');

  const response = await get('student@example.com', db);

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.settings.notifyOnSpinup, false);
  assert.equal(body.settings.notifyOnShutdown, true);
});

test('a guest cannot read them either', async () => {
  const response = await get('guest@example.com', fakeDb());

  assert.equal(response.status, 403);
});
