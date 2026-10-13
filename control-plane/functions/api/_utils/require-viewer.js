// Authorization guard for the read-only endpoints every role may see.
//
// The weakest of the three guards, and still much stronger than none:
// it requires a VERIFIED Cloudflare Access token for this application.
// What it does not do is compare the identity against a list — because
// there is no list to compare against. The three roles are
//
//   ADMIN_EMAIL   the operator
//   USER_EMAIL    the people the stack is for
//   guest emails  whitelist only, no notifications
//
// and the guests are the reason this guard exists in this shape. They are
// on the Access whitelist, they are documented as able to view status,
// services and logs, and the Control Plane is never told who they are:
// `TF_VAR_guest_emails` goes to OpenTofu, which puts the addresses in the
// Access policy, and no step pushes them to the Pages project. So "is
// this caller a guest?" is a question this code cannot answer.
//
// It does not need to. Access issues a token only to an identity its
// policy admits, and `verifyAccessJwt` checks that the token was issued
// by this team FOR this application. A verified token is therefore proof
// of being on the whitelist, which is exactly the membership these
// endpoints require. The identity is not inspected further.
//
// Use it for reads that all three roles are meant to have. Anything that
// changes state, and anything that returns a credential, takes
// requireOperator or requireAdmin instead.
//
// Usage at the top of a handler:
//   const denial = await requireViewer(context.env, context.request);
//   if (denial) return denial;
import { getAccessUserEmail } from './cf-access-email.js';
import { forbidden } from './deny.js';

export async function requireViewer(env, request) {
  // No ADMIN_EMAIL check here, unlike the other two guards: this one
  // never compares against it, so its absence is not what would make
  // this decision wrong.
  const { email, reason } = await getAccessUserEmail(request, env);
  if (email) return null;
  return forbidden('Forbidden: a verified Cloudflare Access session is required', reason);
}
