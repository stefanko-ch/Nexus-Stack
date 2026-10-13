// What this file is for: the previous implementation accepted a token it
// never verified. Every test below would have PASSED against it except the
// ones named "rejects" — so those are the tests that carry the change, and
// they are written against a real signature, not a mock.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  verifyAccessJwt,
  normaliseTeamDomain,
  AccessJwtError,
  _resetJwksCache,
} from '../functions/api/_utils/access-jwt.js';
import { makeKeypair, signToken, forgeUnsignedToken, jwksFetch } from './helpers.mjs';

const OPTS = (fetchImpl) => ({
  teamDomain: 'testteam',
  aud: 'test-aud',
  fetchImpl,
});

async function reason(fn) {
  try {
    await fn();
  } catch (err) {
    assert.ok(err instanceof AccessJwtError, `expected AccessJwtError, got ${err?.name}`);
    return err.reason;
  }
  assert.fail('expected a rejection, got a resolved payload');
}

test('normaliseTeamDomain accepts the three shapes an operator pastes', () => {
  for (const input of [
    'testteam',
    'testteam.cloudflareaccess.com',
    'https://testteam.cloudflareaccess.com',
    'https://testteam.cloudflareaccess.com/',
    '  TestTeam  ',
  ]) {
    assert.equal(normaliseTeamDomain(input), 'testteam.cloudflareaccess.com', input);
  }
  assert.equal(normaliseTeamDomain(''), null);
  assert.equal(normaliseTeamDomain(undefined), null);
});

test('accepts a token signed by the key in the JWKS', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid });
  const payload = await verifyAccessJwt(token, OPTS(jwksFetch([jwk])));
  assert.equal(payload.email, 'admin@example.com');
});

test('rejects a token nobody signed — the bug this file exists for', async () => {
  _resetJwksCache();
  const { jwk } = await makeKeypair();
  const r = await reason(() => verifyAccessJwt(forgeUnsignedToken(), OPTS(jwksFetch([jwk]))));
  assert.equal(r, 'signature does not verify');
});

test('rejects a token signed by a different key with the same kid', async () => {
  _resetJwksCache();
  const real = await makeKeypair('shared-kid');
  const attacker = await makeKeypair('shared-kid');
  const token = await signToken({ privateKey: attacker.privateKey, kid: 'shared-kid' });
  const r = await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([real.jwk]))));
  assert.equal(r, 'signature does not verify');
});

test('rejects alg: none, however well-formed the rest is', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid, header: { alg: 'none' } });
  assert.equal(await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([jwk])))), 'token alg is not RS256');
});

test('rejects HS256, where the "key" would be the public key itself', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid, header: { alg: 'HS256' } });
  assert.equal(await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([jwk])))), 'token alg is not RS256');
});

test('rejects a token from another Access team', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({
    privateKey,
    kid,
    payload: { iss: 'https://someoneelse.cloudflareaccess.com' },
  });
  const r = await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([jwk]))));
  assert.equal(r, 'iss does not match the team domain');
});

test('rejects a token minted for another application', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid, payload: { aud: ['some-other-app'] } });
  const r = await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([jwk]))));
  assert.equal(r, 'aud does not include this application');
});

test('accepts aud as a bare string, per RFC 7519', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid, payload: { aud: 'test-aud' } });
  const payload = await verifyAccessJwt(token, OPTS(jwksFetch([jwk])));
  assert.equal(payload.email, 'admin@example.com');
});

test('rejects an expired token, and allows 60s of skew', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const nowSeconds = Math.floor(Date.now() / 1000);

  const expired = await signToken({ privateKey, kid, payload: { exp: nowSeconds - 120 } });
  assert.equal(await reason(() => verifyAccessJwt(expired, OPTS(jwksFetch([jwk])))), 'token has expired');

  // 30s past exp is inside CLOCK_SKEW_SECONDS and still accepted.
  const justExpired = await signToken({ privateKey, kid, payload: { exp: nowSeconds - 30 } });
  const payload = await verifyAccessJwt(justExpired, OPTS(jwksFetch([jwk])));
  assert.equal(payload.email, 'admin@example.com');
});

test('rejects a token with no exp at all', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid, payload: { exp: undefined } });
  assert.equal(await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([jwk])))), 'token has no exp');
});

test('rejects a token that is not valid yet', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({
    privateKey,
    kid,
    payload: { nbf: Math.floor(Date.now() / 1000) + 600 },
  });
  assert.equal(await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([jwk])))), 'token is not valid yet');
});

test('rejects a kid the JWKS does not contain', async () => {
  _resetJwksCache();
  const { privateKey, jwk } = await makeKeypair('rotated-out');
  const token = await signToken({ privateKey, kid: 'rotated-out' });
  const other = await makeKeypair('current');
  void jwk;
  assert.equal(
    await reason(() => verifyAccessJwt(token, OPTS(jwksFetch([other.jwk])))),
    'token kid is not in the JWKS',
  );
});

test('names the missing configuration instead of failing vaguely', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const token = await signToken({ privateKey, kid });
  const fetchImpl = jwksFetch([jwk]);

  assert.equal(
    await reason(() => verifyAccessJwt(token, { aud: 'test-aud', fetchImpl })),
    'ACCESS_TEAM_DOMAIN is not set',
  );
  assert.equal(
    await reason(() => verifyAccessJwt(token, { teamDomain: 'testteam', fetchImpl })),
    'ACCESS_AUD is not set',
  );
  assert.equal(
    await reason(() => verifyAccessJwt(null, OPTS(fetchImpl))),
    'no Cf-Access-Jwt-Assertion header',
  );
  assert.equal(
    await reason(() => verifyAccessJwt('two.parts', OPTS(fetchImpl))),
    'token is not a three-part JWT',
  );
  assert.equal(
    await reason(() => verifyAccessJwt('not-base64.$$$.sig', OPTS(fetchImpl))),
    'token header or payload is not JSON',
  );
});

test('a JWKS error never carries the upstream body into the reason', async () => {
  _resetJwksCache();
  const secretish = 'account-id-1234-leaked-from-an-error-body';
  const fetchImpl = async () =>
    new Response(secretish, { status: 403, headers: { 'Content-Type': 'text/plain' } });
  const r = await reason(() => verifyAccessJwt(forgeUnsignedToken(), OPTS(fetchImpl)));
  assert.equal(r, 'JWKS endpoint returned HTTP 403');
  assert.ok(!r.includes(secretish));
});

test('a JWKS with no usable keys is an error, not an empty allow', async () => {
  _resetJwksCache();
  const empty = async () => new Response(JSON.stringify({ keys: [] }), { status: 200 });
  assert.equal(await reason(() => verifyAccessJwt(forgeUnsignedToken(), OPTS(empty))), 'JWKS response had no keys');

  _resetJwksCache();
  const junk = async () =>
    new Response(JSON.stringify({ keys: [{ kid: 'x', kty: 'OKP', n: '!!', e: '!!' }] }), { status: 200 });
  assert.equal(
    await reason(() => verifyAccessJwt(forgeUnsignedToken(), OPTS(junk))),
    'JWKS held no importable RS256 keys',
  );
});

test('the JWKS is fetched once per isolate, and from the team domain', async () => {
  _resetJwksCache();
  const { privateKey, jwk, kid } = await makeKeypair();
  const fetchImpl = jwksFetch([jwk]);
  const token = await signToken({ privateKey, kid });

  await verifyAccessJwt(token, OPTS(fetchImpl));
  await verifyAccessJwt(token, OPTS(fetchImpl));

  assert.equal(fetchImpl.calls.length, 1);
  assert.equal(fetchImpl.calls[0], 'https://testteam.cloudflareaccess.com/cdn-cgi/access/certs');
});
