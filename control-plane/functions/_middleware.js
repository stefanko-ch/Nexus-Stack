/**
 * Refuse any request that did not arrive on the Control Plane's own
 * hostname.
 *
 * A Pages project answers on three kinds of hostname:
 *
 *   control.<domain>              the custom domain, with the Access
 *                                 application Terraform creates for it
 *   <project>.pages.dev           the production Pages hostname
 *   <hash>.<project>.pages.dev    one per preview deployment
 *
 * Only the first is covered by this repository. The other two are
 * protected — if at all — by configuration made in the Cloudflare
 * dashboard, which lives outside version control and is not guaranteed to
 * survive a destroy/recreate of the Pages project. This repository
 * destroys and recreates it routinely.
 *
 * So the hostname check belongs in code, where it deploys with the
 * application and covers hostnames nobody has thought of yet. It runs
 * before any route handler, including the ones with no guard of their own.
 *
 * Deliberately NOT a redirect: a redirect to the custom domain would be
 * friendlier for a human who typed the wrong URL, and would also make this
 * an open way to probe which hostnames exist. 404 says the same thing to
 * everyone.
 */
import { expectedHost, isExpectedHost } from './_utils/expected-host.js';

/** Minimal body — this must not describe the deployment to a stranger. */
function notFound() {
  return new Response('Not found', {
    status: 404,
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}

export async function onRequest(context) {
  const { request, env, next } = context;

  // No derivable hostname means DOMAIN is unset, which is a broken
  // deployment rather than a hostile request. Fail closed and say so: the
  // alternative is to serve every hostname, which is the thing this file
  // exists to prevent, and it would do so silently.
  if (!expectedHost(env)) {
    return new Response(
      JSON.stringify({
        success: false,
        error:
          'Server misconfigured: neither CONTROL_PLANE_URL nor DOMAIN is set, ' +
          'so the Control Plane cannot tell which hostname it should answer on.',
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    );
  }

  if (!isExpectedHost(request, env)) return notFound();

  return next();
}
