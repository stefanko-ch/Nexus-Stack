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
 * ONE MARKER PER FAMILY, not one globally. A teardown dispatched while a
 * setup was still waiting to be listed used to overwrite it, and the
 * forgotten family fell straight back into the race this module exists to
 * close. The families are independent, so their markers are too.
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
 *
 * THE WRITE CAN FAIL, and the caller must know. D1 being unavailable is
 * exactly when the duplicate-dispatch race returns, so `markDispatched`
 * reports whether the marker landed instead of swallowing it. The
 * endpoints pass that on as `tracked` and the browser holds its own latch
 * when it is false — see window.NS.status.noteDispatch.
 */

export const DISPATCH_GRACE_MS = 90 * 1000;
export const DISPATCH_MARKER_TTL_MS = 15 * 60 * 1000;

/** Runs created this much before the marker still count as "the new one" — clock skew. */
export const DISPATCH_SKEW_MS = 60 * 1000;

/** Families as status.js buckets them. Anything else is refused, not stored. */
export const DISPATCH_FAMILIES = ['initialSetup', 'setup', 'spinUp', 'teardown', 'destroy'];
const FAMILIES = new Set(DISPATCH_FAMILIES);

const keyFor = (family) => `dispatched_at:${family}`;

/**
 * Record a dispatch.
 *
 * @returns {Promise<boolean>} whether the marker is now stored. False means
 *   status.js will not know about this dispatch — the caller must say so.
 */
export async function markDispatched(db, family) {
  if (!FAMILIES.has(family)) {
    console.error(`dispatch-marker: refusing to store unknown family (${String(family).slice(0, 40)})`);
    return false;
  }
  if (!db) return false;
  try {
    await db
      .prepare('INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, datetime("now"))')
      .bind(keyFor(family), new Date().toISOString())
      .run();
    return true;
  } catch (error) {
    console.error('dispatch-marker: failed to write to D1:', error);
    return false;
  }
}

/**
 * Every fresh marker, keyed by family.
 *
 * @returns {Promise<Record<string, {at: number, ageMs: number}>>}
 *   `at` is epoch ms. Malformed values and anything older than TTL_MS are
 *   dropped — callers never see a stale marker.
 */
export async function readDispatchMarkers(db, now = Date.now()) {
  if (!db) return {};
  const keys = DISPATCH_FAMILIES.map(keyFor);
  let rows;
  try {
    const placeholders = keys.map(() => '?').join(', ');
    const result = await db
      .prepare(`SELECT key, value FROM config WHERE key IN (${placeholders})`)
      .bind(...keys)
      .all();
    rows = result && Array.isArray(result.results) ? result.results : [];
  } catch (error) {
    console.error('dispatch-marker: failed to read from D1:', error);
    return {};
  }
  const out = {};
  for (const row of rows) {
    const family = DISPATCH_FAMILIES.find((f) => keyFor(f) === row.key);
    if (!family) continue;
    const at = Date.parse(row.value || '');
    if (!Number.isFinite(at)) continue;
    const ageMs = now - at;
    if (ageMs < 0 || ageMs > DISPATCH_MARKER_TTL_MS) continue;
    out[family] = { at, ageMs };
  }
  return out;
}
