// A rule, not a snapshot: every request handler under functions/api must
// name a guard, and a handler that needs none must say so here.
//
// The reason this is a test and not a review habit: the five endpoints this
// branch guarded had been unguarded since they were written, each one added
// by someone who reasonably assumed Cloudflare Access covered it. The next
// endpoint will be added by someone with the same reasonable assumption.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const API_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'functions', 'api');

// Handlers that are deliberately reachable without an identity. Each entry
// is a claim about the response, checked by the assertions below — adding a
// name here is not enough to exempt it.
const INTENTIONALLY_UNGUARDED = {
  // Fixed strings and a timestamp. An uptime check has no Access token.
  'health.js': ['onRequestGet'],
  // A public GitHub release tag. Header.astro fetches it on every render,
  // for every Access identity including ones on neither operator list.
  'version.js': ['onRequestGet'],
};

function handlers(source) {
  const marks = [...source.matchAll(/export async function (onRequest\w+)/g)].map((m) => ({
    name: m[1],
    start: m.index,
  }));
  return marks.map((mark, i) => ({
    name: mark.name,
    body: source.slice(mark.start, i + 1 < marks.length ? marks[i + 1].start : source.length),
  }));
}

const files = readdirSync(API_DIR)
  .filter((f) => f.endsWith('.js'))
  .map((f) => ({ name: f, source: readFileSync(path.join(API_DIR, f), 'utf8') }));

test('the API directory is actually being read', () => {
  // A path typo would otherwise make every assertion below vacuous.
  assert.ok(files.length > 15, `expected the api/ handlers, found ${files.length} files`);
});

test('every API handler either calls a guard or is listed as unguarded', () => {
  const missing = [];
  for (const { name, source } of files) {
    for (const { name: handler, body } of handlers(source)) {
      const guarded = /await require(Admin|Operator|Viewer)\(/.test(body);
      const exempt = (INTENTIONALLY_UNGUARDED[name] || []).includes(handler);
      if (guarded && exempt) missing.push(`${name}:${handler} is guarded but listed as unguarded`);
      if (!guarded && !exempt) missing.push(`${name}:${handler} has no identity guard`);
    }
  }
  assert.deepEqual(missing, []);
});

test('no handler calls a guard without awaiting it', () => {
  // `requireAdmin` returns a Promise, and a Promise is truthy — so a
  // forgotten await turns "deny" into "return the denial object as if it
  // were a Response", which fails in a way nothing here would catch.
  const bad = [];
  for (const { name, source } of files) {
    for (const m of source.matchAll(/(.{0,8})require(Admin|Operator|Viewer)\(/g)) {
      if (!m[1].endsWith('await ')) bad.push(`${name}: ${m[0].trim()}`);
    }
  }
  assert.deepEqual(bad, []);
});

test('the unguarded handlers return no deployment state', () => {
  // The exemption is "this response is already public", so it must not
  // read D1, KV, or any configured secret. TEMPLATE_VERSION and the
  // GitHub owner/repo are allowed: a release tag and this repository's
  // own coordinates, both printed in the README.
  const allowed = new Set(['TEMPLATE_VERSION', 'GITHUB_TOKEN', 'GITHUB_OWNER', 'GITHUB_REPO']);
  for (const file of Object.keys(INTENTIONALLY_UNGUARDED)) {
    const source = files.find((f) => f.name === file).source;
    assert.ok(!/NEXUS_DB|NEXUS_KV/.test(source), `${file} reads a datastore but is unguarded`);
    for (const m of source.matchAll(/\benv\.([A-Z][A-Z0-9_]*)/g)) {
      assert.ok(allowed.has(m[1]), `${file} reads env.${m[1]} but is unguarded`);
    }
  }
});

test('nothing reads the Cf-Access-Authenticated-User-Email header any more', () => {
  // That header is set by Cloudflare — and by anyone else who can reach
  // the origin. It is the value this branch stopped trusting, so a new
  // read of it is a regression, not a shortcut.
  const offenders = [];
  for (const { name, source } of files) {
    if (/Cf-Access-Authenticated-User-Email/i.test(source)) offenders.push(name);
  }
  assert.deepEqual(offenders, []);
});

test('the identity helper is only reached through the guards or with an env', () => {
  // getAccessUserEmail(request) — the old one-argument shape — now
  // silently reads `env.ACCESS_TEAM_DOMAIN` off undefined and throws.
  const bad = [];
  for (const { name, source } of files) {
    for (const m of source.matchAll(/getAccessUserEmail\(([^)]*)\)/g)) {
      const args = m[1].split(',').map((a) => a.trim()).filter(Boolean);
      if (args.length < 2) bad.push(`${name}: getAccessUserEmail(${m[1]})`);
    }
  }
  assert.deepEqual(bad, []);
});
