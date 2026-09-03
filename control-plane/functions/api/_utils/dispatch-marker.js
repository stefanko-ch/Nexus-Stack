/**
 * Remember that a workflow was just dispatched, so /api/status does not
 * mistake the previous run for the new one.
 *
 * THE RACE THIS CLOSES. `POST …/dispatches` answers 204 with no run id,
 * and for several seconds afterwards the new run is not in
 * `GET /actions/runs` at all. The dashboard re-polls 2 s after the click,
 * status.js picks the newest run of that workflow — the one that finished
 * an hour ago — reports `deployed`, and the Spin Up button comes back.
 * `spin-up.yml` carries no concurrency lock, so the second click starts a
 * second run. Seen in the wild; this is the fix.
 *
 * Stored in D1 rather than the browser: a reload or a second tab must see
 * the same picture, and the endpoints that dispatch already write to D1.
 *
 * TWO WINDOWS, deliberately different:
 *   GRACE_MS   how long status.js keeps saying "dispatching" while no
 *              matching run has appeared. GitHub usually lists the run
 *              within ~10 s; 90 s is generous. After that the UI says the
 *              run could not be found and points at GitHub.
 *   TTL_MS     how long the marker influences run selection at all. It
 *              hides runs older than the dispatch, which is right while the
 *              new one is expected — and wrong forever if the dispatch
 *              silently produced no run. After 15 min the marker is inert.
 */

export const DISPATCH_GRACE_MS = 90 * 1000;
export const DISPATCH_MARKER_TTL_MS = 15 * 60 * 1000;

/** Runs created this much before the marker still count as "the new one" — clock skew. */
export const DISPATCH_SKEW_MS = 60 * 1000;

const KEY_AT = 'dispatched_at';
const KEY_WORKFLOW = 'dispatched_workflow';

/** Families as status.js buckets them. Anything else is refused, not stored. */
const FAMILIES = new Set(['initialSetup', 'setup', 'spinUp', 'teardown', 'destroy']);

/**
 * Record a dispatch. Best-effort like the logger — a failure here must not
 * turn a successful dispatch into a reported failure — but it is logged,
 * because a missing marker is exactly the race coming back.
 */
export async function markDispatched(db, family) {
  if (!db) return;
  if (!FAMILIES.has(family)) {
    console.error(`dispatch-marker: refusing to store unknown family (${String(family).slice(0, 40)})`);
    return;
  }
  try {
    const now = new Date().toISOString();
    await db.batch([
      db.prepare('INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, datetime("now"))').bind(KEY_AT, now),
      db.prepare('INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, datetime("now"))').bind(KEY_WORKFLOW, family),
    ]);
  } catch (error) {
    console.error('dispatch-marker: failed to write to D1:', error);
  }
}

/**
 * @returns {Promise<{family: string, at: number, ageMs: number} | null>}
 *   `at` is epoch ms. Null when there is no marker, it is malformed, or it
 *   is older than TTL_MS — callers never see a stale marker.
 */
export async function readDispatchMarker(db, now = Date.now()) {
  if (!db) return null;
  let rows;
  try {
    const result = await db
      .prepare('SELECT key, value FROM config WHERE key IN (?, ?)')
      .bind(KEY_AT, KEY_WORKFLOW)
      .all();
    rows = result && Array.isArray(result.results) ? result.results : [];
  } catch (error) {
    console.error('dispatch-marker: failed to read from D1:', error);
    return null;
  }
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  const family = byKey[KEY_WORKFLOW];
  const at = Date.parse(byKey[KEY_AT] || '');
  if (!FAMILIES.has(family) || !Number.isFinite(at)) return null;
  const ageMs = now - at;
  if (ageMs < 0 || ageMs > DISPATCH_MARKER_TTL_MS) return null;
  return { family, at, ageMs };
}
