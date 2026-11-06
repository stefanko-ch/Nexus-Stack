// GET /api/me: the signed-in identity shown in the header.
//
// Real tokens against a real JWKS, as in guards.test.mjs: the endpoint is
// only worth having if it reports the VERIFIED caller, so a test that
// stubbed the verification would prove nothing.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { onRequestGet, roleFor } from '../functions/api/me.js';
import { _resetJwksCache } from '../functions/api/_utils/access-jwt.js';
import { makeKeypair, signToken, forgeUnsignedToken, jwksFetch, request, requestWithToken } from './helpers.mjs';

const ENV = {
  ADMIN_EMAIL: 'admin@example.com',
  USER_EMAIL: 'student@example.com, other@example.com',
  ACCESS_TEAM_DOMAIN: 'testteam',
  ACCESS_AUD: 'test-aud',
};

const URL = 'https://control.example.com/api/me';

async function withJwks(jwks, fn) {
  const original = globalThis.fetch;
  globalThis.fetch = jwksFetch(jwks);
  _resetJwksCache();
  try {
    return await fn();
  } finally {
    globalThis.fetch = original;
    _resetJwksCache();
  }
}

async function me(email) {
  const { privateKey, jwk, kid } = await makeKeypair();
  return withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email } });
    const response = await onRequestGet({ env: ENV, request: requestWithToken(token, URL) });
    return { response, body: JSON.parse(await response.text()) };
  });
}

test('the admin is reported as admin', async () => {
  const { response, body } = await me('admin@example.com');
  assert.equal(response.status, 200);
  assert.deepEqual(body, { success: true, email: 'admin@example.com', role: 'admin' });
});

test('an address from the USER_EMAIL list is a user, whatever its case', async () => {
  const { body } = await me('Other@Example.com');
  assert.equal(body.role, 'user');
  assert.equal(body.email, 'Other@Example.com');
});

test('a verified identity on neither list is a guest', async () => {
  const { body } = await me('guest@example.com');
  assert.equal(body.role, 'guest');
});

test('the answer is never cached for anyone else', async () => {
  const { response } = await me('student@example.com');
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store');
});

test('no token, no identity', async () => {
  const response = await onRequestGet({ env: ENV, request: request(URL) });
  assert.equal(response.status, 403);
});

test('an unsigned token is refused, not reported', async () => {
  const { jwk } = await makeKeypair();
  await withJwks([jwk], async () => {
    const response = await onRequestGet({ env: ENV, request: requestWithToken(forgeUnsignedToken(), URL) });
    assert.equal(response.status, 403);
    assert.ok(!(await response.text()).includes('admin@example.com'));
  });
});

test('without ADMIN_EMAIL nobody is promoted to admin', () => {
  assert.equal(roleFor({ USER_EMAIL: '' }, ''), 'guest');
  assert.equal(roleFor({}, 'admin@example.com'), 'guest');
});
