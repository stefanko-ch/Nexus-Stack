// Denial responses shared by the authorization guards.

/**
 * Shared denial bodies. A misconfigured deployment and a wrong identity
 * must not look the same: the first is for the operator to fix, the
 * second is the guard doing its job.
 */
export function misconfigured(detail) {
  return new Response(
    JSON.stringify({ success: false, error: `Server misconfigured: ${detail}` }),
    { status: 500, headers: { 'Content-Type': 'application/json' } },
  );
}

export function forbidden(message, reason) {
  return new Response(
    // `reason` is produced by access-jwt.js and never contains any part of
    // the token — see AccessJwtError.
    JSON.stringify({ success: false, error: message, reason: reason || undefined }),
    { status: 403, headers: { 'Content-Type': 'application/json' } },
  );
}
