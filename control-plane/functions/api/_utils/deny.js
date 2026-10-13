// Denial responses shared by the authorization guards.
//
// Two kinds of denial, kept apart on purpose:
//
//   misconfigured  nobody can do this, because the deployment is broken
//   forbidden      this caller may not do this
//
// A caller that collapses them shows a student a read-only page and an
// operator a read-only page, when only one of those is the truth. The
// marker header below is how a caller tells them apart without parsing a
// body it did not produce — see `isConfigurationDenial`.

/** Header naming why a denial happened. Internal; never relied on by the UI. */
const DENIAL_KIND_HEADER = 'X-Nexus-Denial';

export function misconfigured(detail) {
  return new Response(
    JSON.stringify({ success: false, error: `Server misconfigured: ${detail}` }),
    {
      status: 500,
      headers: { 'Content-Type': 'application/json', [DENIAL_KIND_HEADER]: 'configuration' },
    },
  );
}

/**
 * @param {string} message  shown to the caller
 * @param {string|null} reason  set only when the guard could not VERIFY the
 *   caller — a missing ACCESS_AUD, an unreachable JWKS, an expired token.
 *   Absent for the ordinary case of a verified identity that simply is not
 *   the one this endpoint needs. Produced by access-jwt.js, so it never
 *   contains any part of the token.
 */
export function forbidden(message, reason) {
  return new Response(
    JSON.stringify({ success: false, error: message, reason: reason || undefined }),
    {
      status: 403,
      headers: {
        'Content-Type': 'application/json',
        // A reason means verification failed, which is a configuration or
        // infrastructure problem rather than this caller's standing.
        [DENIAL_KIND_HEADER]: reason ? 'configuration' : 'identity',
      },
    },
  );
}

/**
 * Whether a denial from one of the guards says "the deployment is broken"
 * rather than "not you".
 *
 * For callers that use a guard to ASK about standing instead of to refuse —
 * /api/lifecycle reports `canEdit` so the page can render the control as
 * read-only. Reporting a broken deployment as "not you" would hide it
 * behind a page that looks deliberately read-only to everyone.
 */
export function isConfigurationDenial(response) {
  return response?.headers?.get(DENIAL_KIND_HEADER) === 'configuration';
}
