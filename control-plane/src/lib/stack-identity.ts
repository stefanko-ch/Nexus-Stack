/**
 * Which stack is this panel? Baked in at build time.
 *
 * Two Nexus-Stack panels are pixel-identical — same logo, same header,
 * same buttons, one of which is Teardown. With a Conductor-Stack and a
 * production stack open in neighbouring tabs, only the URL tells them
 * apart, and the URL is the one thing an operator is not looking at while
 * reaching for a button.
 *
 * Read from `process.env`, not from a Pages binding or an API call.
 * `npm run build` runs on the GitHub runner (spin-up.yml and
 * setup-control-plane.yaml) and `wrangler pages deploy` uploads the
 * finished `dist`, so Cloudflare's own `environment_variables` never reach
 * this build — and `wrangler pages deploy` deletes Terraform-managed ones
 * anyway (see the comment in tofu/control-plane/main.tf). Fetching it at
 * runtime would also make the badge arrive *after* the buttons are
 * clickable, which defeats the point.
 */

/** Empty means "look exactly as before". */
export const stackLabel: string = (process.env.STACK_LABEL ?? '').trim();

/**
 * Operator-supplied and interpolated into a style attribute, so it is
 * constrained rather than trusted: a CSS hex colour or a bare colour
 * keyword. Anything else is dropped and the panel keeps its own accent —
 * a wrong colour is a cosmetic problem, an unvalidated one is a stylesheet
 * an operator can write into every page.
 *
 * The hex lengths are the four CSS actually defines — 3, 4, 6, 8 — not a
 * 3..8 range. Five or seven digits are not a colour, and letting one
 * through is worse than rejecting it: a custom property accepts any token
 * sequence, so `#fffff` would *replace* the `var(--accent)` fallback and
 * only then turn out to be invalid where it is used, leaving the badge
 * with no accent at all rather than the panel's own.
 */
const ACCENT_PATTERN = /^(#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})|[a-zA-Z]{3,20})$/;

const rawAccent = (process.env.STACK_ACCENT ?? '').trim();
export const stackAccent: string = ACCENT_PATTERN.test(rawAccent) ? rawAccent : '';
