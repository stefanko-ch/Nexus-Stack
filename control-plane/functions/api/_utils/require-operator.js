// Authorization guard for endpoints a stack's users may drive themselves.
//
// Sits between requireAdmin and no guard at all, because the Access
// whitelist holds three roles with different standing:
//
//   ADMIN_EMAIL   the operator. Full access, including SSH.
//   USER_EMAIL    the people the stack is for — students on a teaching
//                 stack. May be a comma-separated list. All services
//                 except SSH, and they receive notifications.
//   GUEST_EMAILS  whitelist only, no notifications. Present to let
//                 somebody look, not to let them act.
//
// Cloudflare Access authenticates all three identically, so without a
// guard every endpoint is open to guests, and with requireAdmin it is
// closed to the very people the stack exists for. Starting and stopping
// your own stack is the reason the Control Plane is there; a guest doing
// it to a stack somebody else is working on is not.
//
// Use it where the action is self-service. Today that is exactly three
// endpoints: /api/spin-up, /api/teardown and the POST on /api/services.
//
// Keep requireAdmin everywhere else, including two that sound like they
// belong here and do not. /api/lifecycle changes WHICH teardown and
// spin-up pair the stack uses, which decides what survives a cycle —
// a configuration choice with data-loss consequences, not an act of
// running the stack. /api/scheduled-teardown sets the cost-control
// timer that users are not meant to switch off. The rest is plainly
// operator work: destroying infrastructure, redeploying the Control
// Plane, opening host firewall ports, mailing the Infisical master
// credentials.
//
// Usage at the top of a handler, after the origin check:
//   const denial = requireOperator(context.env, context.request);
//   if (denial) return denial;
import { getAccessUserEmail } from './cf-access-email.js';

export function requireOperator(env, request) {
  const adminEmail = (env.ADMIN_EMAIL || '').trim().toLowerCase();
  if (!adminEmail) {
    // Same failure mode as requireAdmin: with no admin configured there
    // is no identity to compare against, and treating that as "allow"
    // would turn a misconfiguration into an open endpoint.
    return new Response(
      JSON.stringify({
        success: false,
        error: 'Server misconfigured: ADMIN_EMAIL is not set',
      }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // USER_EMAIL may be a single address or a comma-separated list — the
  // same shape send-credentials.js already parses. An unset value leaves
  // only the admin, which is the correct single-operator behaviour.
  const userEmails = (env.USER_EMAIL || '')
    .split(',')
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);

  // Comparison is case-insensitive to match Cloudflare Access and
  // identity-provider behaviour, as requireAdmin does.
  const caller = (getAccessUserEmail(request) || '').trim().toLowerCase();
  if (caller && (caller === adminEmail || userEmails.includes(caller))) {
    return null;
  }

  return new Response(
    JSON.stringify({
      success: false,
      error: 'Forbidden: this endpoint requires an operator or user account',
    }),
    { status: 403, headers: { 'Content-Type': 'application/json' } }
  );
}
