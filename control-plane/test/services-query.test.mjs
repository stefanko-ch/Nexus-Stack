// GET /api/services must keep answering while D1 still lacks the `tier`
// column (#712): spin-up.yml deploys Pages before it migrates D1.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { selectServices } from '../functions/api/_utils/services-query.js';

/** A D1 stand-in whose `services` table has exactly `columns`. */
function fakeDb(columns) {
  const queries = [];
  return {
    queries,
    prepare(sql) {
      queries.push(sql);
      const statement = {
        bind(...args) {
          statement.args = args;
          return statement;
        },
        async all() {
          const selected = sql.match(/SELECT (.*) FROM/)[1].split(',').map((c) => c.trim());
          const missing = selected.find((c) => !columns.includes(c));
          if (missing) throw new Error(`D1_ERROR: no such column: ${missing}: SQLITE_ERROR`);
          return { results: [{ name: 'kestra', tier: columns.includes('tier') ? 'proven' : undefined }] };
        },
      };
      return statement;
    },
  };
}

const OLD = ['name', 'enabled', 'deployed', 'subdomain', 'port', 'public', 'core', 'admin_only',
  'description', 'category', 'website', 'long_description', 'landing_path', 'api_only'];

test('reads tier once the column exists', async () => {
  const db = fakeDb([...OLD, 'tier']);
  const result = await selectServices(db, null);
  assert.equal(result.results[0].tier, 'proven');
  assert.equal(db.queries.length, 1);
});

test('falls back to the old columns before the migration ran', async () => {
  const db = fakeDb(OLD);
  const result = await selectServices(db, 'orchestration');
  assert.equal(result.results[0].name, 'kestra');
  assert.equal(db.queries.length, 2);
  assert.match(db.queries[1], /WHERE category = \?/);
  assert.doesNotMatch(db.queries[1], /tier/);
});

test('any other error still fails the request', async () => {
  const db = fakeDb(OLD.filter((c) => c !== 'api_only'));
  await assert.rejects(selectServices(db, null), /no such column: api_only/);
});
