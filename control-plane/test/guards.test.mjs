// The guards, end to end: a request goes in, a denial or null comes out.
//
// The central assertion is `self-set headers no longer pass`. Both headers
// the old implementation trusted are set explicitly here, with no token,
// and the guard must still deny — that case passed before this change.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { requireAdmin } from '../functions/api/_utils/require-admin.js';
import { requireOperator } from '../functions/api/_utils/require-operator.js';
import { requireViewer } from '../functions/api/_utils/require-viewer.js';
import { getAccessUserEmail } from '../functions/api/_utils/cf-access-email.js';
import { _resetJwksCache } from '../functions/api/_utils/access-jwt.js';
import { makeKeypair, signToken, forgeUnsignedToken, jwksFetch, request, requestWithToken } from './helpers.mjs';

const ENV = {
  ADMIN_EMAIL: 'admin@example.com',
  USER_EMAIL: 'student@example.com, other@example.com',
  ACCESS_TEAM_DOMAIN: 'testteam',
  ACCESS_AUD: 'test-aud',
};

/** Run `fn` with globalThis.fetch serving `jwks`, then restore it. */
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

async function body(response) {
  return JSON.parse(await response.text());
}

test('requireViewer admits an identity on neither list, with a real token', async () => {
  // A guest. The Control Plane is never told who the guests are — the
  // addresses go to the Access policy, not to the Pages project — so a
  // verified token for this application IS the membership proof, and
  // that is what this guard checks.
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: 'guest@example.com' } });
    assert.equal(await requireViewer(ENV, requestWithToken(token)), null);
  });
});

test('requireViewer still refuses an unverified token', async () => {
  const { jwk } = await makeKeypair();
  await withJwks([jwk], async () => {
    const denial = await requireViewer(ENV, requestWithToken(forgeUnsignedToken()));
    assert.equal(denial.status, 403);
    assert.equal((await body(denial)).reason, 'signature does not verify');
  });
});

test('requireViewer refuses a token minted for a different application', async () => {
  // The whole membership argument rests on `aud`: a token from another
  // Access application in the same account is not proof of being on THIS
  // application's whitelist.
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { aud: ['some-other-app'] } });
    const denial = await requireViewer(ENV, requestWithToken(token));
    assert.equal(denial.status, 403);
    assert.equal((await body(denial)).reason, 'aud does not include this application');
  });
});

test('requireViewer does not depend on ADMIN_EMAIL being set', async () => {
  // It never compares against it, so an unset ADMIN_EMAIL must not turn
  // a read into a 500 — unlike the other two guards, where it must.
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: 'guest@example.com' } });
    assert.equal(await requireViewer({ ...ENV, ADMIN_EMAIL: '' }, requestWithToken(token)), null);
  });
});

test('a self-set Cf-Access header does not pass either guard', async () => {
  const { jwk } = await makeKeypair();
  await withJwks([jwk], async () => {
    const forged = request('https://control.example.com/api/secrets', {
      'Cf-Access-Authenticated-User-Email': 'admin@example.com',
      'Cf-Access-Jwt-Assertion': forgeUnsignedToken(),
    });

    for (const [name, guard] of [['requireAdmin', requireAdmin], ['requireOperator', requireOperator]]) {
      const denial = await guard(ENV, forged);
      assert.ok(denial, `${name} let a forged request through`);
      assert.equal(denial.status, 403, name);
      assert.equal((await body(denial)).reason, 'signature does not verify', name);
    }
  });
});

test('no token at all is a named 403, not a crash', async () => {
  const { jwk } = await makeKeypair();
  await withJwks([jwk], async () => {
    const denial = await requireAdmin(ENV, request());
    assert.equal(denial.status, 403);
    assert.equal((await body(denial)).reason, 'no Cf-Access-Jwt-Assertion header');
  });
});

test('the admin passes requireAdmin with a real token', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: 'admin@example.com' } });
    assert.equal(await requireAdmin(ENV, requestWithToken(token)), null);
  });
});

test('a user with a real token is denied by requireAdmin and admitted by requireOperator', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: 'student@example.com' } });

    const denial = await requireAdmin(ENV, requestWithToken(token));
    assert.equal(denial.status, 403);
    // A real identity that is simply not the admin: no `reason`, because
    // nothing is misconfigured. This is the guard working.
    assert.equal((await body(denial)).reason, undefined);

    assert.equal(await requireOperator(ENV, requestWithToken(token)), null);
  });
});

test('email comparison is case-insensitive in both guards', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const admin = await signToken({ privateKey, kid, payload: { email: 'Admin@Example.COM' } });
    assert.equal(await requireAdmin(ENV, requestWithToken(admin)), null);

    const user = await signToken({ privateKey, kid, payload: { email: ' STUDENT@example.com ' } });
    assert.equal(await requireOperator(ENV, requestWithToken(user)), null);
  });
});

test('an identity on neither list is denied by requireOperator', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: 'guest@example.com' } });
    const denial = await requireOperator(ENV, requestWithToken(token));
    assert.equal(denial.status, 403);
  });
});

test('a verified token with no email claim is not an identity', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: undefined } });
    const denial = await requireAdmin(ENV, requestWithToken(token));
    assert.equal(denial.status, 403);
    assert.equal((await body(denial)).reason, 'token carries no email claim');
  });
});

test('an unset ADMIN_EMAIL is a 500 naming the variable, not an open endpoint', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid });
    for (const guard of [requireAdmin, requireOperator]) {
      const denial = await guard({ ...ENV, ADMIN_EMAIL: '' }, requestWithToken(token));
      assert.equal(denial.status, 500);
      assert.match((await body(denial)).error, /ADMIN_EMAIL/);
    }
  });
});

test('missing ACCESS_AUD / ACCESS_TEAM_DOMAIN deny, and say which one', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid });

    const noAud = await requireAdmin({ ...ENV, ACCESS_AUD: '' }, requestWithToken(token));
    assert.equal(noAud.status, 403);
    assert.equal((await body(noAud)).reason, 'ACCESS_AUD is not set');

    const noTeam = await requireAdmin({ ...ENV, ACCESS_TEAM_DOMAIN: '' }, requestWithToken(token));
    assert.equal(noTeam.status, 403);
    assert.equal((await body(noTeam)).reason, 'ACCESS_TEAM_DOMAIN is not set');
  });
});

test('USER_EMAIL unset leaves the admin as the only operator', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const env = { ...ENV, USER_EMAIL: '' };
    const admin = await signToken({ privateKey, kid, payload: { email: 'admin@example.com' } });
    assert.equal(await requireOperator(env, requestWithToken(admin)), null);

    const student = await signToken({ privateKey, kid, payload: { email: 'student@example.com' } });
    assert.equal((await requireOperator(env, requestWithToken(student))).status, 403);
  });
});

test('getAccessUserEmail returns null rather than any fallback identity', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const forged = request('https://control.example.com/api/secrets', {
      'Cf-Access-Authenticated-User-Email': 'admin@example.com',
    });
    assert.deepEqual(await getAccessUserEmail(forged, ENV), {
      email: null,
      reason: 'no Cf-Access-Jwt-Assertion header',
    });

    const token = await signToken({ privateKey, kid });
    assert.deepEqual(await getAccessUserEmail(requestWithToken(token), ENV), {
      email: 'admin@example.com',
      reason: null,
    });
  });
});

test('a denial body never carries the token or any part of it', async () => {
  const { privateKey, jwk, kid } = await makeKeypair();
  await withJwks([jwk], async () => {
    const token = await signToken({ privateKey, kid, payload: { email: 'guest@example.com' } });
    const denial = await requireAdmin(ENV, requestWithToken(token));
    const text = await denial.text();
    for (const part of token.split('.')) {
      assert.ok(!text.includes(part), 'denial body leaked part of the token');
    }
  });
});
