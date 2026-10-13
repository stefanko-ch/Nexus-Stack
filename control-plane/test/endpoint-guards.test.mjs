// A rule, not a snapshot: every request handler under functions/api must
// name a guard, and a handler that needs none must say so here.
//
// The reason this is a test and not a review habit: the five endpoints this
// branch guarded had been unguarded since they were written, each one added
// by someone who reasonably assumed Cloudflare Access covered it. The next
// endpoint will be added by someone with the same reasonable assumption.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
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

/** Code with comments removed: prose is not behaviour. */
function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

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

/**
 * Every routed handler file under functions/api, recursively.
 *
 * Pages Functions route subdirectories — `api/foo/bar.js` serves
 * `/api/foo/bar` — so a check that read only the top level would skip a
 * nested endpoint and let an unguarded route ship. There are no such
 * directories today; the recursion is so that adding one does not
 * silently opt out of every rule below.
 *
 * `_`-prefixed names are skipped because Pages does not route them: that
 * is what makes `_utils/` helpers and not endpoints.
 */
function handlerFiles(dir, prefix = '') {
  const out = [];
  for (const entry of readdirSync(dir).sort()) {
    if (entry.startsWith('_')) continue;
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...handlerFiles(full, `${prefix}${entry}/`));
    } else if (entry.endsWith('.js')) {
      out.push({ name: `${prefix}${entry}`, source: readFileSync(full, 'utf8') });
    }
  }
  return out;
}

const files = handlerFiles(API_DIR);

test('every test file in this directory is one the runner picks up', () => {
  // The suite is run as `node --test test/*.test.mjs`, so a file named
  // anything else is silently never executed — a gap that looks exactly
  // like a passing suite. `helpers.mjs` is imported, not run.
  const here = path.dirname(fileURLToPath(import.meta.url));
  const stray = readdirSync(here).filter(
    (f) => f.endsWith('.mjs') && !f.endsWith('.test.mjs') && f !== 'helpers.mjs',
  );
  assert.deepEqual(stray, []);
});

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

test('the guard runs before the handler touches anything', () => {
  // "Calls a guard somewhere in the body" is not the rule — a guard after
  // the first database read has already leaked the read. So the awaited
  // guard must come before the first use of a datastore binding or an
  // outbound fetch, and before any try block that might contain one.
  const late = [];
  for (const { name, source } of files) {
    for (const { name: handler, body } of handlers(source)) {
      if ((INTENTIONALLY_UNGUARDED[name] || []).includes(handler)) continue;
      const code = stripComments(body);
      const guardAt = code.search(/await require(Admin|Operator|Viewer)\(/);
      if (guardAt === -1) {
        late.push(`${name}:${handler} has no guard in its code (only in a comment?)`);
        continue;
      }
      // Datastore access by any spelling — `env.NEXUS_DB`,
      // `context.env.NEXUS_DB`, or destructured to a bare binding — plus
      // reading the request body, calling out, and `try {`, which can
      // contain any of them.
      const firstUse = [
        /\bNEXUS_DB\b/,
        /\bNEXUS_KV\b/,
        /\.prepare\(/,
        /\brequest\.(json|text|arrayBuffer|formData)\(/,
        /\bfetchWithTimeout\(/,
        /\bfetch\(/,
        /\btry\s*\{/,
      ]
        .map((re) => code.search(re))
        .filter((i) => i !== -1);
      const earliest = firstUse.length ? Math.min(...firstUse) : Infinity;
      if (earliest < guardAt) late.push(`${name}:${handler} reads state before its guard`);
    }
  }
  assert.deepEqual(late, []);
});

test('every guard result is returned, not merely obtained', () => {
  // Calling and awaiting a guard proves nothing if the denial is then
  // dropped: the handler carries on and serves the protected response to
  // a caller the guard just refused. So the value the guard was assigned
  // to must appear in a `return` soon after.
  //
  // "Soon after" rather than "on the next line", because two handlers
  // legitimately do more with it: firewall.js picks the guard with a
  // ternary, and lifecycle.js returns it only when it is a configuration
  // denial, using the rest to decide `canEdit`.
  const dropped = [];
  for (const { name, source } of files) {
    for (const { name: handler, body } of handlers(source)) {
      const code = stripComments(body);
      for (const m of code.matchAll(/(?:const|let)\s+(\w+)\s*=\s*(?:await\s+require|countOnly)/g)) {
        const variable = m[1];
        const after = code.slice(m.index, m.index + 400);
        if (!new RegExp(`return\\s+${variable}\\b`).test(after)) {
          dropped.push(`${name}:${handler} obtains ${variable} from a guard and never returns it`);
        }
      }
    }
  }
  assert.deepEqual(dropped, []);
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
