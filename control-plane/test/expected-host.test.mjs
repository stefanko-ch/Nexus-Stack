import { test } from 'node:test';
import assert from 'node:assert/strict';

import { expectedHost, isExpectedHost } from '../functions/_utils/expected-host.js';
import { onRequest } from '../functions/_middleware.js';
import { request } from './helpers.mjs';

const ENV = { CONTROL_PLANE_URL: 'https://control.example.com' };

test('CONTROL_PLANE_URL is the canonical source', () => {
  assert.equal(expectedHost(ENV), 'control.example.com');
  assert.equal(expectedHost({ CONTROL_PLANE_URL: 'https://CONTROL.Example.COM/' }), 'control.example.com');
});

test('falls back to DOMAIN with the subdomain separator', () => {
  assert.equal(expectedHost({ DOMAIN: 'example.com' }), 'control.example.com');
  assert.equal(
    expectedHost({ DOMAIN: 'example.com', SUBDOMAIN_SEPARATOR: '-' }),
    'control-example.com',
  );
  // An empty separator is the workflow's "unset", not a request for
  // `controlexample.com`.
  assert.equal(expectedHost({ DOMAIN: 'example.com', SUBDOMAIN_SEPARATOR: '  ' }), 'control.example.com');
});

test('CONTROL_PLANE_URL wins over DOMAIN when both are set', () => {
  assert.equal(
    expectedHost({ CONTROL_PLANE_URL: 'https://panel.example.com', DOMAIN: 'other.com' }),
    'panel.example.com',
  );
});

test('a non-https or unparseable CONTROL_PLANE_URL falls through to DOMAIN', () => {
  for (const url of ['http://control.example.com', 'control.example.com', 'not a url', '']) {
    assert.equal(expectedHost({ CONTROL_PLANE_URL: url, DOMAIN: 'example.com' }), 'control.example.com', url);
  }
});

test('no derivable hostname yields null, not a guess', () => {
  assert.equal(expectedHost({}), null);
  assert.equal(expectedHost({ SUBDOMAIN_SEPARATOR: '-' }), null);
  assert.equal(expectedHost({ CONTROL_PLANE_URL: 'http://nope' }), null);
});

test('isExpectedHost compares case-insensitively and ignores port-less paths', () => {
  assert.equal(isExpectedHost(request('https://control.example.com/api/info'), ENV), true);
  assert.equal(isExpectedHost(request('https://CONTROL.EXAMPLE.COM/'), ENV), true);
  assert.equal(isExpectedHost(request('https://nexus-control.pages.dev/api/info'), ENV), false);
  assert.equal(isExpectedHost(request('https://abc123.nexus-control.pages.dev/'), ENV), false);
  // A suffix match must not pass: this is the shape a wildcard check gets wrong.
  assert.equal(isExpectedHost(request('https://evil-control.example.com/'), ENV), false);
  assert.equal(isExpectedHost(request('https://control.example.com.evil.test/'), ENV), false);
});

test('isExpectedHost is false when nothing is configured', () => {
  assert.equal(isExpectedHost(request('https://control.example.com/'), {}), false);
});

function nextSpy() {
  const spy = async () => new Response('handler ran', { status: 200 });
  return spy;
}

test('the middleware serves the Control Plane hostname', async () => {
  let ran = false;
  const next = async () => {
    ran = true;
    return new Response('ok', { status: 200 });
  };
  const response = await onRequest({ request: request('https://control.example.com/api/info'), env: ENV, next });
  assert.equal(response.status, 200);
  assert.equal(ran, true);
});

test('the middleware 404s every other hostname, including previews', async () => {
  for (const url of [
    'https://nexus-control.pages.dev/api/secrets',
    'https://9f2c.nexus-control.pages.dev/api/secrets',
    'https://control.example.com.evil.test/api/secrets',
  ]) {
    let ran = false;
    const response = await onRequest({
      request: request(url),
      env: ENV,
      next: async () => {
        ran = true;
        return new Response('handler ran', { status: 200 });
      },
    });
    assert.equal(response.status, 404, url);
    assert.equal(ran, false, `${url} reached the handler`);
    // 404 and not a redirect: a redirect would confirm which hostname is real.
    assert.equal(response.headers.get('Location'), null);
    const body = await response.text();
    assert.equal(body, 'Not found');
  }
});

test('the middleware refuses to serve anything when it cannot tell its own hostname', async () => {
  const response = await onRequest({
    request: request('https://control.example.com/api/secrets'),
    env: {},
    next: nextSpy(),
  });
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.success, false);
  // Names the cause: "misconfigured" with no noun is the message that
  // sends an operator to the wrong place.
  assert.match(body.error, /CONTROL_PLANE_URL/);
  assert.match(body.error, /DOMAIN/);
});
