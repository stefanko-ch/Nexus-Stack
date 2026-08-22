/**
 * Which lifecycle workflow the Control Plane dispatches.
 *
 * Nexus-Stack has two teardown/spin-up pairs:
 *
 *   teardown.yml / spin-up.yml                    destroy and rebuild from
 *                                                 ubuntu-24.04
 *   teardown-snapshot.yml / spin-up-snapshot.yml  snapshot the disk, destroy
 *                                                 only the server, restore
 *                                                 from the image
 *
 * The pair in use is a D1 config value rather than a code change, so
 * switching is one row and rolling back is the same row. Defaults are the
 * legacy names, so an unconfigured stack behaves exactly as before.
 *
 * WHY AN ALLOWLIST: these values are interpolated into a GitHub API URL
 * (`/actions/workflows/<value>/dispatches`). Anything unexpected in the
 * config table would become part of that path. Only the four known
 * filenames are accepted; anything else falls back to the legacy default
 * and is reported, rather than being passed through.
 *
 * ⚠️ The two must be switched TOGETHER. A snapshot teardown followed by a
 * legacy spin-up wastes the image; a legacy teardown runs an untargeted
 * `tofu destroy` that rotates all 81 generated credentials, which makes
 * every existing snapshot unrestorable — the epoch guard then correctly
 * refuses it and falls back to a fresh build.
 */

export const TEARDOWN_WORKFLOWS = ['teardown.yml', 'teardown-snapshot.yml'];
export const SPINUP_WORKFLOWS = ['spin-up.yml', 'spin-up-snapshot.yml'];

export const DEFAULT_TEARDOWN_WORKFLOW = 'teardown.yml';
export const DEFAULT_SPINUP_WORKFLOW = 'spin-up.yml';

/**
 * Read one workflow name from D1, validated against its allowlist.
 *
 * Falls back to `fallback` when the key is unset, when D1 is unreachable,
 * or when the stored value is not on the allowlist. Never throws: a
 * Control Plane that cannot read its own config should still be able to
 * tear down, and doing so on the legacy path is the safe default.
 *
 * @param {D1Database|undefined} db
 * @param {string} key            config key, e.g. 'teardown_workflow'
 * @param {string[]} allowed      permitted filenames
 * @param {string} fallback       value to use when unset or invalid
 * @returns {Promise<string>}
 */
export async function getWorkflowName(db, key, allowed, fallback) {
  if (!db) return fallback;
  try {
    const row = await db
      .prepare('SELECT value FROM config WHERE key = ?')
      .bind(key)
      .first();
    const value = row ? row.value : null;
    if (!value) return fallback;
    if (!allowed.includes(value)) {
      console.error(
        `config.${key} is not a known workflow: ${JSON.stringify(value)} — using ${fallback}`
      );
      return fallback;
    }
    return value;
  } catch (error) {
    console.error(`Failed to read config.${key} from D1:`, error);
    return fallback;
  }
}

/** The teardown workflow this stack is configured to use. */
export function getTeardownWorkflow(db) {
  return getWorkflowName(
    db,
    'teardown_workflow',
    TEARDOWN_WORKFLOWS,
    DEFAULT_TEARDOWN_WORKFLOW
  );
}

/** The spin-up workflow this stack is configured to use. */
export function getSpinUpWorkflow(db) {
  return getWorkflowName(
    db,
    'spinup_workflow',
    SPINUP_WORKFLOWS,
    DEFAULT_SPINUP_WORKFLOW
  );
}
