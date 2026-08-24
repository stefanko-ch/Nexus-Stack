// CSRF guard for state-changing endpoints.
//
// Cloudflare Access authenticates the caller, but authentication is not
// the same as intent. Access identity travels in a cookie, so a browser
// that is logged in sends it on *any* request to this origin — including
// one triggered by a page the operator did not write. The endpoint then
// sees a valid admin and does as it is told.
//
// TWO CHECKS, because either alone leaves a gap:
//
// 1. Content-Type must be JSON. A cross-site HTML form can only send
//    urlencoded, multipart, or text/plain — it cannot set
//    application/json without a CORS preflight the browser will refuse.
//    This matters more than it looks: `request.json()` does not care
//    what the Content-Type says, so a form with enctype="text/plain"
//    and a carefully named field produces a body that parses as valid
//    JSON. Requiring the header closes that door.
//
// 2. Origin, when present, must match. Browsers attach Origin to every
//    cross-origin request and to same-origin POSTs. A mismatch is a
//    cross-site submission and nothing else.
//
// A MISSING Origin is allowed on purpose: curl, the CLI and any
// server-to-server caller send none, and those are legitimate. They also
// cannot be driven by a victim's browser, which is the whole threat
// here. The Content-Type check still applies to them.
const deny = (reason) =>
  new Response(JSON.stringify({ success: false, error: reason }), {
    status: 403,
    headers: { 'Content-Type': 'application/json' },
  });

/**
 * Returns a 403 Response to return immediately, or null when the request
 * may proceed. Mirrors requireAdmin's shape so handlers read the same:
 *
 *   const blocked = requireSameOrigin(request);
 *   if (blocked) return blocked;
 */
export function requireSameOrigin(request) {
  const contentType = (request.headers.get('Content-Type') || '').toLowerCase();
  if (!contentType.includes('application/json')) {
    return deny('Content-Type must be application/json');
  }

  const origin = request.headers.get('Origin');
  if (!origin) return null;

  let expected;
  try {
    expected = new URL(request.url).origin;
  } catch {
    // An unparseable request URL should never happen. Fail closed rather
    // than guess, since the only caller is a state-changing endpoint.
    return deny('Could not determine the request origin');
  }

  return origin === expected ? null : deny('Cross-origin request refused');
}
