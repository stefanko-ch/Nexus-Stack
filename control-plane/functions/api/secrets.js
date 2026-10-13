/**
 * GET /api/secrets — Fetches secrets live from Infisical, grouped by folder.
 *
 * Thin wrapper around fetchAllInfisicalSecrets() — the fetch logic is shared
 * with POST /api/databricks-sync so the Secrets page and the Databricks scope
 * always mirror the same inventory.
 *
 * This returns secret VALUES in plaintext, so it carries the strongest
 * guard an endpoint users need to reach can have: `requireOperator`, which
 * admits the admin and the addresses in USER_EMAIL and nobody else. It
 * previously had none, on the reasoning that Cloudflare Access in front of
 * the custom domain was enough — a guarantee this repository cannot make,
 * because the Pages project answers on hostnames Terraform does not cover.
 */
import { fetchAllInfisicalSecrets } from './_utils/infisical.js';
import { requireOperator } from './_utils/require-operator.js';

export async function onRequestGet(context) {
  const denial = await requireOperator(context.env, context.request);
  if (denial) return denial;

  try {
    const { configured, groups, warnings, message } = await fetchAllInfisicalSecrets(context.env);

    if (!configured) {
      return Response.json({ success: true, groups: [], message });
    }

    const response = { success: true, groups };
    if (warnings && warnings.length > 0) response.warnings = warnings;
    return Response.json(response);
  } catch (error) {
    return Response.json({ success: false, error: error.message }, { status: 500 });
  }
}
