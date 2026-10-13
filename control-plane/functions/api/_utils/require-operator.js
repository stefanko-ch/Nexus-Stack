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
// Use it where the action is self-service, or where the response is a
// credential. Today that is four endpoints: /api/spin-up, /api/teardown,
// the POST on /api/services, and GET /api/secrets — which returns secret
// VALUES, so guests are deliberately not admitted to it even though they
// may see the dashboard around it.
//
// For reads that all three roles are meant to have, requireViewer sits one
// tier below this one: it requires a verified Access session without
// comparing the identity to a list, because the Control Plane is never
// told who the guests are. See require-viewer.js.
//
// Keep requireAdmin everywhere else, including two that sound like they
// belong here and do not. /api/lifecycle changes WHICH teardown and
// spin-up pair the stack uses, which decides what survives a cycle —
// a configuration choice with data-loss consequences, not an act of
// running the stack. The POST on /api/scheduled-teardown sets the
// cost-control timer that users are not meant to switch off (its GET is
// viewer-level: the dashboard shows the countdown to everyone). The rest is plainly
// operator work: destroying infrastructure, redeploying the Control
// Plane, opening host firewall ports, mailing the Infisical master
// credentials.
//
// Usage at the top of a handler, after the origin check:
//   const denial = await requireOperator(context.env, context.request);
//   if (denial) return denial;
import { getAccessUserEmail } from './cf-access-email.js';
import { misconfigured, forbidden } from './deny.js';

export async function requireOperator(env, request) {
  const adminEmail = (env.ADMIN_EMAIL || '').trim().toLowerCase();
  if (!adminEmail) {
    // Same failure mode as requireAdmin: with no admin configured there
    // is no identity to compare against, and treating that as "allow"
    // would turn a misconfiguration into an open endpoint.
    return misconfigured('ADMIN_EMAIL is not set');
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
  const { email, reason } = await getAccessUserEmail(request, env);
  const caller = (email || '').trim().toLowerCase();
  if (caller && (caller === adminEmail || userEmails.includes(caller))) return null;

  return forbidden('Forbidden: this endpoint requires an operator or user account', reason);
}
