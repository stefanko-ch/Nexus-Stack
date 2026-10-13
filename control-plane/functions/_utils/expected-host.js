/**
 * The one hostname this Control Plane is meant to be reached on.
 *
 * A Pages project is served on its custom domain AND on
 * `<project>.pages.dev`, plus a hostname per preview deployment. Terraform
 * creates the Access application for the custom domain only, so the others
 * depend on configuration made elsewhere — in a dashboard, outside this
 * repository, and therefore not guaranteed to survive a destroy/recreate
 * cycle of the Pages project.
 *
 * This module is what lets the code stop depending on that. It is kept
 * separate from `_middleware.js` so it can be unit-tested without a
 * request.
 */

/** Hostname of `value` if it parses as an https: URL, else null. */
function hostOfHttpsUrl(value) {
  if (!value) return null;
  try {
    const u = new URL(value);
    return u.protocol === 'https:' ? u.hostname.toLowerCase() : null;
  } catch {
    return null;
  }
}

/**
 * Derive the expected hostname from the environment.
 *
 * Two sources, in order:
 *
 * 1. `CONTROL_PLANE_URL` — the canonical value, set as a Pages secret by
 *    setup-control-plane.yaml. It is NOT guaranteed: that step only sets
 *    it when DOMAIN *and* SUBDOMAIN_SEPARATOR are both non-empty, which is
 *    why the existing callers in `send-credentials.js` treat it as
 *    optional too.
 * 2. `control<SUBDOMAIN_SEPARATOR><DOMAIN>` — the same composition the
 *    workflow uses, with `.` as the separator default, matching
 *    `var.subdomain_separator` in tofu/control-plane.
 *
 * Returns null when neither yields a hostname. The caller decides what
 * that means; see `_middleware.js`, which refuses the request rather than
 * guessing.
 */
export function expectedHost(env) {
  const fromUrl = hostOfHttpsUrl(env.CONTROL_PLANE_URL);
  if (fromUrl) return fromUrl;

  const domain = (env.DOMAIN || '').trim().toLowerCase();
  if (!domain) return null;
  const separator = (env.SUBDOMAIN_SEPARATOR || '.').trim() || '.';
  return `control${separator}${domain}`;
}

/**
 * Whether `request` arrived on the expected hostname.
 *
 * Compares against the URL's own hostname rather than the `Host` header:
 * at this point Cloudflare has already routed the request, and
 * `new URL(request.url).hostname` is what it routed on. A `Host` header
 * read directly would be the attacker-supplied one on some proxy setups.
 */
export function isExpectedHost(request, env) {
  const expected = expectedHost(env);
  if (!expected) return false;
  try {
    return new URL(request.url).hostname.toLowerCase() === expected;
  } catch {
    return false;
  }
}
