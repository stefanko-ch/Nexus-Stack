/**
 * The services SELECT behind GET /api/services.
 *
 * `tier` (#712) is the one column the frontend may ask for before it
 * exists. setup-control-plane.yaml adds it before its own Pages deploy, but
 * spin-up.yml deploys Pages before sync-deployed-state.sh migrates D1, so
 * on an existing database the new frontend can run against the old schema
 * for a few minutes. Retrying without the column keeps the Stacks pages up
 * for that window; every row then reads as best-effort, which is what a
 * missing badge already says.
 */

const BASE_COLUMNS =
  'name, enabled, deployed, subdomain, port, public, core, admin_only, description, ' +
  'category, website, long_description, landing_path, api_only';

function prepare(db, columns, categoryFilter) {
  if (categoryFilter) {
    return db
      .prepare(`SELECT ${columns} FROM services WHERE category = ? ORDER BY name`)
      .bind(categoryFilter);
  }
  return db.prepare(`SELECT ${columns} FROM services ORDER BY name`);
}

export async function selectServices(db, categoryFilter) {
  try {
    return await prepare(db, `${BASE_COLUMNS}, tier`, categoryFilter).all();
  } catch (error) {
    if (!/no such column:\s*tier/i.test(String(error && error.message))) throw error;
    return await prepare(db, BASE_COLUMNS, categoryFilter).all();
  }
}
