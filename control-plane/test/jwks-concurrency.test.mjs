// Concurrency around the JWKS, which is where a cache of a remote key set
// goes wrong: a stampede on a cold isolate, two fetches finishing out of
// order, and a request that arrives while a rotation is being picked up.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { verifyAccessJwt, AccessJwtError, _resetJwksCache } from '../functions/api/_utils/access-jwt.js';
import { makeKeypair, signToken } from './helpers.mjs';

const OPTS = (fetchImpl, now) => ({ teamDomain: 'testteam', aud: 'test-aud', fetchImpl, now });

/** Same, with a JWKS timeout short enough to wait for in a test. */
const FAST_TIMEOUT = (fetchImpl) => ({ ...OPTS(fetchImpl), jwksTimeoutMs: 50 });

/** A fetch whose responses are released by the test, one at a time. */
function gatedFetch() {
  const pending = [];
  const impl = async () => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    pending.push(release);
    const keys = await gate;
    return new Response(JSON.stringify({ keys }), { status: 200 });
  };
  impl.pending = pending;
  /** Release the Nth outstanding fetch with `keys`. */
  impl.release = (index, keys) => pending[index](keys);
  return impl;
}

test('a burst on a cold cache makes one outbound request, not one each', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const fetchImpl = gatedFetch();
  const token = await signToken({ privateKey, kid });

  const verifications = [
    verifyAccessJwt(token, OPTS(fetchImpl)),
    verifyAccessJwt(token, OPTS(fetchImpl)),
    verifyAccessJwt(token, OPTS(fetchImpl)),
  ];

  // Let the first (and, if coalescing works, only) fetch start.
  await new Promise((r) => setImmediate(r));
  assert.equal(fetchImpl.pending.length, 1, 'each verification started its own fetch');

  fetchImpl.release(0, [jwk]);
  const payloads = await Promise.all(verifications);
  assert.deepEqual(payloads.map((p) => p.email), Array(3).fill('admin@example.com'));
  assert.equal(fetchImpl.pending.length, 1);
});

test('a request arriving mid-rotation waits for the refresh instead of being refused', async () => {
  _resetJwksCache();
  const old = await makeKeypair('old-kid');
  const fresh = await makeKeypair('new-kid');
  const clock = { ms: 5_000_000 };
  const now = () => clock.ms;
  const fetchImpl = gatedFetch();

  // Warm the cache with the pre-rotation key set.
  const warm = verifyAccessJwt(await signToken({ privateKey: old.privateKey, kid: 'old-kid' }), OPTS(fetchImpl, now));
  await new Promise((r) => setImmediate(r));
  fetchImpl.release(0, [old.jwk]);
  await warm;

  // Two requests carrying the rotated kid arrive together. The first
  // starts the forced refresh and stamps the cooldown; the second must
  // await that refresh rather than reading the stamp as "refused".
  const rotated = await signToken({ privateKey: fresh.privateKey, kid: 'new-kid' });
  const first = verifyAccessJwt(rotated, OPTS(fetchImpl, now));
  await new Promise((r) => setImmediate(r));
  assert.equal(fetchImpl.pending.length, 2, 'the kid miss should have started a refresh');
  const second = verifyAccessJwt(rotated, OPTS(fetchImpl, now));
  await new Promise((r) => setImmediate(r));
  assert.equal(fetchImpl.pending.length, 2, 'the second request started a third fetch');

  fetchImpl.release(1, [fresh.jwk]);
  for (const payload of await Promise.all([first, second])) {
    assert.equal(payload.email, 'admin@example.com');
  }
});

test('an overlapping fetch cannot install an older key set as the fresh one', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair('stable-kid');
  const stale = await makeKeypair('stale-kid');
  const fetchImpl = gatedFetch();
  const token = await signToken({ privateKey, kid });

  // Two verifications on a cold cache. With coalescing there is one
  // fetch, so there is no second response that could land last and
  // overwrite the first — which is the failure this asserts against.
  const both = Promise.all([
    verifyAccessJwt(token, OPTS(fetchImpl)),
    verifyAccessJwt(token, OPTS(fetchImpl)),
  ]);
  await new Promise((r) => setImmediate(r));
  assert.equal(fetchImpl.pending.length, 1);
  fetchImpl.release(0, [jwk]);
  await both;

  // The cache now holds the key both requests used. A later verification
  // reads it without any fetch at all.
  const again = await verifyAccessJwt(token, OPTS(fetchImpl));
  assert.equal(again.email, 'admin@example.com');
  assert.equal(fetchImpl.pending.length, 1);
  void stale;
});

test('an in-flight refresh for another team is not mistaken for this one', async () => {
  // One team domain per deployment makes this unreachable in production.
  // It is here because the check that makes it unreachable is one `&&`
  // that is easy to drop — and the first version of this test did not
  // reach that check at all: it asserted on fetch COUNT, which
  // `fetchJwks` already keeps correct by its own URL comparison, so the
  // mutation passed. The path that matters is the one in `keyForKid`,
  // which needs a warm cache plus a kid miss to be reached.
  _resetJwksCache();
  const warm = await makeKeypair('warm-kid');
  const rotated = await makeKeypair('rotated-kid');
  const theirs = await makeKeypair('their-kid');

  const pending = [];
  const fetchImpl = async (url) => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    pending.push({ url, release });
    return new Response(JSON.stringify({ keys: await gate }), { status: 200 });
  };
  const forTeam = (team) => ({ teamDomain: team, aud: 'test-aud', fetchImpl });

  // 1. Warm OUR cache, so the next lookup needs no fetch of its own.
  const first = verifyAccessJwt(await signToken({ privateKey: warm.privateKey, kid: 'warm-kid' }), forTeam('testteam'));
  await new Promise((r) => setImmediate(r));
  pending[0].release([warm.jwk]);
  assert.equal((await first).email, 'admin@example.com');

  // 2. Hold a fetch open for a DIFFERENT team, so `jwksInFlight` is set
  //    and points somewhere else.
  const other = verifyAccessJwt(await signToken({ privateKey: theirs.privateKey, kid: 'their-kid' }), forTeam('otherteam'))
    .catch(() => 'rejected');
  await new Promise((r) => setImmediate(r));
  assert.equal(pending.length, 2);
  assert.match(pending[1].url, /otherteam/);

  // 3. Our rotated kid misses our warm cache, which lands in `keyForKid`'s
  //    in-flight branch. Without the URL comparison it awaits the other
  //    team's key set, does not find our kid, and rejects a valid token.
  const mine = verifyAccessJwt(await signToken({ privateKey: rotated.privateKey, kid: 'rotated-kid' }), forTeam('testteam'));
  await new Promise((r) => setImmediate(r));
  const ourRefresh = pending.find((c, i) => i > 1 && /testteam/.test(c.url));
  assert.ok(ourRefresh, 'the kid miss should have started a refresh for OUR team');
  ourRefresh.release([rotated.jwk]);
  assert.equal((await mine).email, 'admin@example.com');

  pending[1].release([theirs.jwk]);
  await other;
});

test('a stalled JWKS endpoint produces a prompt denial, not a hang', { timeout: 5000 }, async () => {
  _resetJwksCache();
  // Never resolves, and never settles the abort either — the only way
  // out is the AbortSignal the fetch is given.
  const stalling = async (_url, { signal }) =>
    new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(signal.reason ?? new DOMException('Aborted', 'AbortError')));
    });

  const { privateKey, jwk, kid } = await makeKeypair();
  void jwk;
  const token = await signToken({ privateKey, kid });

  await assert.rejects(
    () => verifyAccessJwt(token, FAST_TIMEOUT(stalling)),
    (err) => {
      assert.ok(err instanceof AccessJwtError);
      // Named, so a log says "the JWKS endpoint is unreachable" rather
      // than something that reads like a bad token.
      assert.equal(err.reason, 'JWKS fetch timed out');
      return true;
    },
  );
});

test('a failed fetch does not poison the cache for the next request', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid });

  let attempt = 0;
  const flaky = async () => {
    attempt += 1;
    if (attempt === 1) return new Response('upstream is sad', { status: 502 });
    return new Response(JSON.stringify({ keys: [jwk] }), { status: 200 });
  };

  await assert.rejects(() => verifyAccessJwt(token, OPTS(flaky)), AccessJwtError);
  // The second attempt must be allowed to fetch: a rejected fetch
  // installs nothing, so there is no cache entry and no in-flight
  // promise left behind to serve the failure again.
  const payload = await verifyAccessJwt(token, OPTS(flaky));
  assert.equal(payload.email, 'admin@example.com');
  assert.equal(attempt, 2);
});
