// Test helpers: a real RSA keypair, a real JWKS, real signatures.
//
// Nothing here stubs the verification. `crypto.subtle` in Node is the same
// Web Crypto API the Workers runtime exposes, so a token this file signs is
// verified by exactly the code that runs in production — which is the point:
// a test that mocked the signature check would pass just as happily against
// the unverified-header implementation this replaces.

const encoder = new TextEncoder();

function b64url(bytes) {
  const binary = String.fromCharCode(...new Uint8Array(bytes));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlJson(value) {
  return b64url(encoder.encode(JSON.stringify(value)));
}

const ALGORITHM = { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' };

/** A fresh keypair plus the JWKS entry that matches it. */
export async function makeKeypair(kid = 'test-kid') {
  const { publicKey, privateKey } = await crypto.subtle.generateKey(
    { ...ALGORITHM, modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]) },
    true,
    ['sign', 'verify'],
  );
  const jwk = await crypto.subtle.exportKey('jwk', publicKey);
  return { privateKey, jwk: { kid, kty: jwk.kty, n: jwk.n, e: jwk.e, alg: 'RS256', use: 'sig' }, kid };
}

/**
 * Sign a token. `header` and `payload` are merged over the defaults, so a
 * test can break exactly one thing and leave the rest valid.
 */
export async function signToken({ privateKey, kid, payload = {}, header = {} }) {
  const fullHeader = { alg: 'RS256', kid, ...header };
  const fullPayload = {
    iss: 'https://testteam.cloudflareaccess.com',
    aud: ['test-aud'],
    email: 'admin@example.com',
    exp: Math.floor(Date.now() / 1000) + 3600,
    ...payload,
  };
  const signingInput = `${b64urlJson(fullHeader)}.${b64urlJson(fullPayload)}`;
  const signature = await crypto.subtle.sign(ALGORITHM, privateKey, encoder.encode(signingInput));
  return `${signingInput}.${b64url(signature)}`;
}

/** An unsigned token: valid-looking header and payload, random signature. */
export function forgeUnsignedToken(payload = {}) {
  const header = b64urlJson({ alg: 'RS256', kid: 'test-kid' });
  const body = b64urlJson({
    iss: 'https://testteam.cloudflareaccess.com',
    aud: ['test-aud'],
    email: 'admin@example.com',
    exp: Math.floor(Date.now() / 1000) + 3600,
    ...payload,
  });
  return `${header}.${body}.${b64url(encoder.encode('not-a-signature'))}`;
}

/** A fetch stand-in that serves `jwks` and records every call. */
export function jwksFetch(jwks) {
  const calls = [];
  const impl = async (url) => {
    calls.push(url);
    return new Response(JSON.stringify({ keys: jwks }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  impl.calls = calls;
  return impl;
}

export function request(url = 'https://control.example.com/api/secrets', headers = {}) {
  return new Request(url, { headers });
}

/** A request carrying a verified-looking token. */
export function requestWithToken(token, url) {
  return request(url, { 'Cf-Access-Jwt-Assertion': token });
}
