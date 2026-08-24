// Read and change which teardown/spin-up pair this stack uses.
//
// Nexus-Stack has two lifecycles and they are a genuine choice, not a
// migration with an old and a new side:
//
//   rebuild   Destroy everything, rebuild from ubuntu-24.04 on the next
//             spin-up. Fresh OS and freshly pulled images every time, so
//             nothing drifts and `:latest` stacks stay current. Costs a
//             few minutes per spin-up, and anything not covered by the
//             R2 persistence layer is gone — that layer protects Gitea,
//             Dify, HedgeDoc, Planka and Metabase by name, so a stack's
//             own Postgres tables, Grafana dashboards, Kestra run
//             history and uncommitted notebooks are not included.
//
//   snapshot  Snapshot the disk before destroying the server, restore
//             from that image on the next spin-up. Every stack's state
//             survives, not only the five, and the boot skips apt and
//             the Docker install. In exchange the images age: a `:latest`
//             stack keeps whatever was pulled when the snapshot line
//             began.
//
// Which one is right depends on how the stack is used, which is why it
// is a setting rather than a decision baked into the code.
//
// WRITES ARE ADMIN-ONLY. Switching is not reversible in effect: moving
// from snapshot to rebuild means the next teardown runs an untargeted
// `tofu destroy` that rotates all 81 generated credentials, after which
// the epoch guard permanently refuses every existing snapshot. Reading
// is open to any Access-authenticated caller so the UI can show the
// current state without an admin session.
import { getAccessUserEmail } from './_utils/cf-access-email.js';
import { requireAdmin } from './_utils/require-admin.js';
import {
  LIFECYCLE_MODES,
  LIFECYCLE_WORKFLOWS,
  DEFAULT_LIFECYCLE_MODE,
  canonicalMode,
} from './_utils/workflow-selection.js';

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

// Shown in the UI. Kept here rather than in workflow-selection.js so the
// Worker's duplicate of that module stays free of presentation strings.
const MODE_INFO = {
  rebuild: {
    label: 'Rebuild',
    summary: 'Destroy and rebuild from a clean Ubuntu image every time.',
    keeps: 'Only what the R2 layer backs up: Gitea, Dify, HedgeDoc, Planka, Metabase.',
    loses: 'Everything else — your own Postgres tables, Grafana dashboards, Kestra run history, uncommitted notebooks.',
    images: 'Always freshly pulled, so `:latest` stacks stay current.',
  },
  snapshot: {
    label: 'Snapshot',
    summary: 'Snapshot the disk, restore from it on the next spin-up.',
    keeps: 'Everything on the server, across all stacks.',
    loses: 'Nothing, as long as a usable snapshot exists.',
    images: 'Frozen at the snapshot — refresh them explicitly when you want newer ones.',
  },
};

async function readMode(db) {
  const row = await db
    .prepare('SELECT value FROM config WHERE key = ?')
    .bind('lifecycle_mode')
    .first();
  // An absent row is a definite answer, not an unknown: the stack was
  // never switched, so the default applies.
  if (!row || !row.value) return DEFAULT_LIFECYCLE_MODE;
  return canonicalMode(row.value);
}

async function logChange(db, level, message, metadata) {
  // Best-effort: a failed audit write must not fail the request that
  // already succeeded, or the caller retries and switches twice.
  try {
    await db
      .prepare('INSERT INTO logs (source, level, message, metadata) VALUES (?, ?, ?, ?)')
      .bind('lifecycle', level, message, metadata ? JSON.stringify(metadata) : null)
      .run();
  } catch {
    /* ignore */
  }
}

export async function onRequestGet(context) {
  const { env } = context;
  if (!env.NEXUS_DB) {
    return json({ success: false, error: 'D1 database not configured' }, 500);
  }

  try {
    const mode = await readMode(env.NEXUS_DB);
    const known = LIFECYCLE_MODES.includes(mode);
    return json({
      success: true,
      // `null` rather than the raw string when unrecognised: the stored
      // value is unvalidated input and does not belong in a response
      // body any more than it belongs in a log line.
      mode: known ? mode : null,
      recognised: known,
      workflows: known ? LIFECYCLE_WORKFLOWS[mode] : null,
      modes: LIFECYCLE_MODES.map((m) => ({
        value: m,
        ...MODE_INFO[m],
        workflows: LIFECYCLE_WORKFLOWS[m],
      })),
    });
  } catch (error) {
    console.error('lifecycle: failed to read config.lifecycle_mode:', error);
    return json({ success: false, error: 'Could not read the lifecycle mode' }, 500);
  }
}

export async function onRequestPost(context) {
  const { env, request } = context;
  const denial = requireAdmin(env, request);
  if (denial) return denial;

  if (!env.NEXUS_DB) {
    return json({ success: false, error: 'D1 database not configured' }, 500);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ success: false, error: 'Request body must be JSON' }, 400);
  }

  const requested = canonicalMode(body?.mode);
  if (!LIFECYCLE_MODES.includes(requested)) {
    // Echoes the accepted values, never the rejected one.
    return json(
      { success: false, error: `mode must be one of: ${LIFECYCLE_MODES.join(', ')}` },
      400,
    );
  }

  try {
    const previous = await readMode(env.NEXUS_DB);
    if (previous === requested) {
      return json({ success: true, mode: requested, changed: false });
    }

    await env.NEXUS_DB.prepare(
      `INSERT INTO config (key, value, updated_at)
       VALUES ('lifecycle_mode', ?, datetime('now'))
       ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')`,
    )
      .bind(requested)
      .run();

    const userEmail = getAccessUserEmail(request) || 'unknown';
    await logChange(env.NEXUS_DB, 'info', `Lifecycle mode changed to ${requested}`, {
      from: previous,
      to: requested,
      by: userEmail,
    });

    return json({
      success: true,
      mode: requested,
      changed: true,
      previous,
      workflows: LIFECYCLE_WORKFLOWS[requested],
      // Surfaced so the UI can warn rather than the operator finding out
      // at the next teardown.
      warning:
        requested === 'rebuild'
          ? 'Switching to Rebuild rotates every generated credential on the next teardown. Existing snapshots will be refused from then on and cannot be restored.'
          : null,
    });
  } catch (error) {
    console.error('lifecycle: failed to write config.lifecycle_mode:', error);
    return json({ success: false, error: 'Could not save the lifecycle mode' }, 500);
  }
}
