/**
 * Which lifecycle workflow pair the Control Plane dispatches.
 *
 * Nexus-Stack has two pairs:
 *
 *   legacy    teardown.yml / spin-up.yml
 *             destroy everything, rebuild from ubuntu-24.04
 *   snapshot  teardown-snapshot.yml / spin-up-snapshot.yml
 *             snapshot the disk, destroy only the server, restore from
 *             the image
 *
 * ONE config value, not two. The pair is selected by `lifecycle_mode`
 * ('legacy' | 'snapshot') and both workflow names are derived from it.
 *
 * Two independent keys were the first design and it was wrong: they can
 * drift, and a half-applied switch is actively harmful. Snapshot spin-up
 * with legacy teardown means the nightly untargeted `tofu destroy`
 * rotates all 81 generated credentials, and the epoch guard then refuses
 * the snapshot it just made. Documenting "switch both together" is not
 * the same as making it impossible to do otherwise.
 *
 * WHY AN ALLOWLIST: the derived names are interpolated into a GitHub API
 * URL path (`/actions/workflows/<name>/dispatches`). Deriving them from a
 * validated mode rather than reading them from the database means no
 * database value ever reaches that path.
 *
 * "CANNOT TELL" IS NOT "NOT CONFIGURED". These are different answers and
 * the caller must be able to tell them apart:
 *
 *   absent      no row -> the stack was never switched -> legacy is right
 *   unreadable  D1 down, no binding, unknown value -> we do not know which
 *               mode this stack is in, and guessing legacy would dispatch
 *               the DESTRUCTIVE pair at a stack that may be on snapshots
 *
 * That is why this returns a result rather than a bare string with a
 * fallback baked in.
 */

export const LIFECYCLE_MODES = ['legacy', 'snapshot'];
export const DEFAULT_LIFECYCLE_MODE = 'legacy';

/** Workflow filenames per mode. The only place these strings live. */
export const LIFECYCLE_WORKFLOWS = {
  legacy: { teardown: 'teardown.yml', spinUp: 'spin-up.yml' },
  snapshot: { teardown: 'teardown-snapshot.yml', spinUp: 'spin-up-snapshot.yml' },
};

/** Every filename either mode can produce — for run detection, not dispatch. */
export const ALL_TEARDOWN_WORKFLOWS = LIFECYCLE_MODES.map(
  (m) => LIFECYCLE_WORKFLOWS[m].teardown
);
export const ALL_SPINUP_WORKFLOWS = LIFECYCLE_MODES.map(
  (m) => LIFECYCLE_WORKFLOWS[m].spinUp
);

/**
 * Resolve the configured lifecycle mode.
 *
 * @param {D1Database|undefined} db
 * @returns {Promise<{ok: true, mode: string, teardown: string, spinUp: string}
 *                 | {ok: false, reason: string}>}
 *
 * `ok: false` means the configuration could not be determined. Callers
 * must NOT fall back to a default on that — see the note above. It is
 * only returned for a genuine unknown; an unconfigured stack resolves
 * successfully to 'legacy'.
 */
export async function resolveLifecycle(db) {
  if (!db) {
    // Expected during local development, a misconfiguration in
    // production. Either way we cannot know the mode.
    return { ok: false, reason: 'no D1 binding available' };
  }

  let row;
  try {
    row = await db
      .prepare('SELECT value FROM config WHERE key = ?')
      .bind('lifecycle_mode')
      .first();
  } catch (error) {
    // Log the error object, never the row: a config value we failed to
    // validate must not end up in a log line.
    console.error('Failed to read config.lifecycle_mode from D1:', error);
    return { ok: false, reason: 'D1 read failed' };
  }

  const value = row ? row.value : null;

  // No row: this stack was never switched. That is a definite answer,
  // not an unknown one.
  if (!value) {
    return { ok: true, mode: DEFAULT_LIFECYCLE_MODE, ...LIFECYCLE_WORKFLOWS[DEFAULT_LIFECYCLE_MODE] };
  }

  if (!LIFECYCLE_MODES.includes(value)) {
    // Deliberately does not print the value. It is an unvalidated
    // database string, and this project does not put those in logs — if
    // a secret were ever written to the wrong key, the log would keep it.
    console.error(
      `config.lifecycle_mode holds an unrecognised value (expected one of: ${LIFECYCLE_MODES.join(', ')})`
    );
    return { ok: false, reason: 'unrecognised lifecycle_mode' };
  }

  return { ok: true, mode: value, ...LIFECYCLE_WORKFLOWS[value] };
}
