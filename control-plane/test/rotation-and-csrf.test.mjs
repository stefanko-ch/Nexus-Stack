// The second round's additions: key rotation, one verification per
// request, the denial marker, and the origin-only CSRF check.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { verifyAccessJwt, AccessJwtError, _resetJwksCache } from '../functions/api/_utils/access-jwt.js';
import { getAccessUserEmail } from '../functions/api/_utils/cf-access-email.js';
import { requireAdmin } from '../functions/api/_utils/require-admin.js';
import { requireViewer } from '../functions/api/_utils/require-viewer.js';
import { isConfigurationDenial, misconfigured, forbidden } from '../functions/api/_utils/deny.js';
import { requireSameOrigin, requireSameOriginHeader } from '../functions/api/_utils/require-same-origin.js';
import { makeKeypair, signToken, jwksFetch, request, requestWithToken } from './helpers.mjs';

const ENV = {
  ADMIN_EMAIL: 'admin@example.com',
  ACCESS_TEAM_DOMAIN: 'testteam',
  ACCESS_AUD: 'test-aud',
};

/** A fetch stand-in whose key set can change between calls. */
function rotatingFetch(initialKeys) {
  let keys = initialKeys;
  const calls = [];
  const impl = async (url) => {
    calls.push(url);
    return new Response(JSON.stringify({ keys }), { status: 200 });
  };
  impl.calls = calls;
  impl.rotateTo = (next) => {
    keys = next;
  };
  return impl;
}

test('a rotated key is picked up without waiting for the cache to expire', async () => {
  _resetJwksCache();
  const old = await makeKeypair('old-kid');
  const fresh = await makeKeypair('new-kid');
  const fetchImpl = rotatingFetch([old.jwk]);
  const clock = { ms: 1_000_000 };
  const now = () => clock.ms;

  // Warm the cache with the pre-rotation key set.
  const before = await signToken({ privateKey: old.privateKey, kid: 'old-kid' });
  assert.equal((await verifyAccessJwt(before, { teamDomain: 'testteam', aud: 'test-aud', fetchImpl, now })).email, 'admin@example.com');
  assert.equal(fetchImpl.calls.length, 1);

  // Access rotates. The cache is still inside its 10-minute TTL, so
  // without the kid-miss refetch this token would be refused for minutes.
  fetchImpl.rotateTo([fresh.jwk]);
  const after = await signToken({ privateKey: fresh.privateKey, kid: 'new-kid' });
  const payload = await verifyAccessJwt(after, { teamDomain: 'testteam', aud: 'test-aud', fetchImpl, now });
  assert.equal(payload.email, 'admin@example.com');
  assert.equal(fetchImpl.calls.length, 2, 'the unknown kid should have refetched the JWKS');
});

test('a made-up kid does not buy an outbound fetch per attempt', async () => {
  _resetJwksCache();
  const real = await makeKeypair('real-kid');
  const attacker = await makeKeypair('made-up-kid');
  const fetchImpl = rotatingFetch([real.jwk]);
  const clock = { ms: 1_000_000 };
  const now = () => clock.ms;
  const opts = { teamDomain: 'testteam', aud: 'test-aud', fetchImpl, now };

  const token = await signToken({ privateKey: attacker.privateKey, kid: 'made-up-kid' });

  for (let i = 0; i < 20; i += 1) {
    await assert.rejects(() => verifyAccessJwt(token, opts), AccessJwtError);
    clock.ms += 1000; // 20 attempts over 20 seconds
  }
  // One fetch to warm the cache, one miss-triggered refresh. Not 21.
  assert.equal(fetchImpl.calls.length, 2);

  // Past the floor, one more refresh is allowed — so a genuine rotation
  // that happens during an attack is still picked up.
  clock.ms += 61_000;
  await assert.rejects(() => verifyAccessJwt(token, opts), AccessJwtError);
  assert.equal(fetchImpl.calls.length, 3);
});

test('a request is verified once, however many times its identity is asked for', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  const original = globalThis.fetch;
  globalThis.fetch = jwksFetch([jwk]);
  _resetJwksCache();
  try {
    const token = await signToken({ privateKey, kid });
    const req = requestWithToken(token);

    // A guard, then the handler asking who the caller was — the shape in
    // scheduled-teardown.js and send-credentials.js.
    assert.equal(await requireAdmin(ENV, req), null);
    const first = await getAccessUserEmail(req, ENV);
    const second = await getAccessUserEmail(req, ENV);

    assert.equal(first.email, 'admin@example.com');
    // Same object, not merely an equal one: that is what proves the
    // second call did not verify again.
    assert.equal(first, second);
  } finally {
    globalThis.fetch = original;
    _resetJwksCache();
  }
});

test('the memo does not carry between requests', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  const original = globalThis.fetch;
  globalThis.fetch = jwksFetch([jwk]);
  _resetJwksCache();
  try {
    const admin = requestWithToken(await signToken({ privateKey, kid, payload: { email: 'admin@example.com' } }));
    const other = requestWithToken(await signToken({ privateKey, kid, payload: { email: 'someone@example.com' } }));

    assert.equal((await getAccessUserEmail(admin, ENV)).email, 'admin@example.com');
    assert.equal((await getAccessUserEmail(other, ENV)).email, 'someone@example.com');
    assert.equal((await getAccessUserEmail(admin, ENV)).email, 'admin@example.com');
  } finally {
    globalThis.fetch = original;
    _resetJwksCache();
  }
});

test('a configuration denial is distinguishable from "not you"', async () => {
  assert.equal(isConfigurationDenial(misconfigured('ADMIN_EMAIL is not set')), true);
  assert.equal(isConfigurationDenial(forbidden('nope', 'ACCESS_AUD is not set')), true);
  // The ordinary case: a verified identity that is not the admin.
  assert.equal(isConfigurationDenial(forbidden('nope', null)), false);
  // Anything else, including a response from elsewhere.
  assert.equal(isConfigurationDenial(new Response('x', { status: 403 })), false);
  assert.equal(isConfigurationDenial(null), false);
});

test('the guards mark their denials so a caller can tell the two apart', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  const original = globalThis.fetch;
  globalThis.fetch = jwksFetch([jwk]);
  _resetJwksCache();
  try {
    const token = await signToken({ privateKey, kid, payload: { email: 'guest@example.com' } });

    // Not the admin: an ordinary refusal, so /api/lifecycle reports
    // canEdit:false rather than surfacing it as a broken deployment.
    assert.equal(isConfigurationDenial(await requireAdmin(ENV, requestWithToken(token))), false);

    // Cannot verify anything: a broken deployment, surfaced.
    const broken = await requireAdmin({ ...ENV, ACCESS_AUD: '' }, requestWithToken(token));
    assert.equal(isConfigurationDenial(broken), true);
    assert.equal(isConfigurationDenial(await requireViewer({ ...ENV, ACCESS_TEAM_DOMAIN: '' }, requestWithToken(token))), true);
  } finally {
    globalThis.fetch = original;
    _resetJwksCache();
  }
});

test('the origin-only check accepts a bodyless same-origin DELETE', () => {
  const sameOrigin = new Request('https://control.example.com/api/logs?days=30', {
    method: 'DELETE',
    headers: { Origin: 'https://control.example.com', 'Sec-Fetch-Site': 'same-origin' },
  });
  assert.equal(requireSameOriginHeader(sameOrigin), null);

  // The full guard would refuse it, which is why the split exists.
  assert.equal(requireSameOrigin(sameOrigin)?.status, 403);
});

test('the origin-only check refuses a cross-site DELETE', async () => {
  for (const headers of [
    { Origin: 'https://evil.test', 'Sec-Fetch-Site': 'cross-site' },
    { Origin: 'https://evil.test' },
    // No Origin, but the browser still says where it came from.
    { 'Sec-Fetch-Site': 'cross-site' },
    { 'Sec-Fetch-Site': 'same-site' },
  ]) {
    const denial = requireSameOriginHeader(
      new Request('https://control.example.com/api/logs', { method: 'DELETE', headers }),
    );
    assert.equal(denial?.status, 403, JSON.stringify(headers));
  }
});

test('a non-browser caller with no origin headers is still allowed', () => {
  // curl and the CLI send neither header, and neither can be driven by a
  // victim's browser — the documented reason the full guard allows it too.
  const cli = new Request('https://control.example.com/api/logs', { method: 'DELETE' });
  assert.equal(requireSameOriginHeader(cli), null);
});

test('DELETE /api/logs checks the origin before the identity', async () => {
  const { onRequestDelete } = await import('../functions/api/logs.js');
  const crossSite = new Request('https://control.example.com/api/logs?days=30', {
    method: 'DELETE',
    headers: { Origin: 'https://evil.test', 'Sec-Fetch-Site': 'cross-site' },
  });
  // No env bindings at all: if the origin check did not come first, this
  // would fail on something else — a missing NEXUS_DB or an unverifiable
  // token — rather than on the thing being tested.
  const response = await onRequestDelete({ env: {}, request: crossSite });
  assert.equal(response.status, 403);
  assert.match(JSON.parse(await response.text()).error, /[Cc]ross-/);
});

test('the request helper is actually producing distinct Requests', () => {
  // Guards the memo tests above: if `request()` returned a shared object,
  // "the memo does not carry between requests" would be vacuous.
  assert.notEqual(request(), request());
});
