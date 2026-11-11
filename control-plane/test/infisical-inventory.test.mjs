// The Secrets page and the Databricks sync read the whole Infisical
// inventory through one helper. It used to make one subrequest per folder,
// and a Pages Function may make at most 50 per invocation on the free plan:
// the list ended at the 50th folder, and a Databricks sync then deleted the
// keys of every folder it no longer saw (#1036). These tests pin the one
// request and the all-or-nothing result.

import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import {
  fetchAllInfisicalSecrets, groupNameForPath, groupSecrets,
} from '../functions/api/_utils/infisical.js';

const ENV = {
  INFISICAL_TOKEN: 'token',
  INFISICAL_PROJECT_ID: 'project-1',
  DOMAIN: 'example.com',
};

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function captureFetch(respond) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return respond(String(url), init);
  };
  return calls;
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

/** A recursive listing with `folders` folders of two secrets each, plus two at the root. */
function inventory(folders) {
  const secrets = [
    { secretKey: 'ROOT_B', secretValue: 'b', secretPath: '/' },
    { secretKey: 'ROOT_A', secretValue: 'a', secretPath: '/' },
  ];
  for (let i = 0; i < folders; i += 1) {
    const name = `stack-${String(i).padStart(3, '0')}`;
    secrets.push({ secretKey: 'PASSWORD', secretValue: `p${i}`, secretPath: `/${name}` });
    secrets.push({ secretKey: 'USERNAME', secretValue: `u${i}`, secretPath: `/${name}` });
  }
  return { secrets };
}

test('the whole inventory costs one subrequest, however many folders there are', async () => {
  const calls = captureFetch(() => json(inventory(120)));
  const result = await fetchAllInfisicalSecrets(ENV);

  assert.equal(calls.length, 1, 'one request, not one per folder');
  const url = new URL(calls[0].url);
  assert.equal(url.origin, 'https://infisical.example.com');
  assert.equal(url.pathname, '/api/v3/secrets/raw');
  assert.equal(url.searchParams.get('recursive'), 'true');
  assert.equal(url.searchParams.get('secretPath'), '/');
  assert.equal(url.searchParams.get('workspaceId'), 'project-1');
  assert.equal(url.searchParams.get('environment'), 'dev');

  assert.equal(result.configured, true);
  assert.deepEqual(result.warnings, []);
  assert.equal(result.groups.length, 121, '120 folders and the root, none cut off');
  assert.equal(result.groups.at(-1).name, 'stack-119');
});

test('secrets are grouped by folder, sorted, and empty values dropped', () => {
  const groups = groupSecrets([
    { secretKey: 'Z', secretValue: 'z', secretPath: '/portainer' },
    { secretKey: 'A', secretValue: 'a', secretPath: '/portainer' },
    { secretKey: 'EMPTY', secretValue: '', secretPath: '/portainer' },
    { secretKey: 'HIDDEN', secretPath: '/mage' },
    { secretKey: 'TOP', secretValue: 't', secretPath: '/' },
  ]);
  assert.deepEqual(groups, [
    { name: 'portainer', secrets: [{ key: 'A', value: 'a' }, { key: 'Z', value: 'z' }] },
    { name: 'root', secrets: [{ key: 'TOP', value: 't' }] },
  ]);
});

test('a folder path becomes its group name', () => {
  assert.equal(groupNameForPath('/portainer'), 'portainer');
  assert.equal(groupNameForPath('/portainer/'), 'portainer');
  assert.equal(groupNameForPath('/a/b'), 'a/b');
  assert.equal(groupNameForPath('/'), 'root');
  assert.equal(groupNameForPath(undefined), 'root');
});

test('a failed request throws instead of returning part of the inventory', async () => {
  captureFetch(() => new Response('upstream down', { status: 503 }));
  await assert.rejects(fetchAllInfisicalSecrets(ENV), /Failed to fetch secrets from Infisical \(503\)/);
});

test('a non-JSON answer (an Access login page) throws', async () => {
  captureFetch(() => new Response('<html>login</html>', { status: 200, headers: { 'content-type': 'text/html' } }));
  await assert.rejects(fetchAllInfisicalSecrets(ENV), /non-JSON response/);
});

test('without the Infisical settings nothing is fetched', async () => {
  const calls = captureFetch(() => json({ secrets: [] }));
  const result = await fetchAllInfisicalSecrets({ DOMAIN: 'example.com' });
  assert.equal(result.configured, false);
  assert.equal(calls.length, 0);
});
