/**
 * Who is looking at this Control Plane
 * GET /api/me
 *
 * Returns the verified caller's email and which of the three roles it
 * holds, so Header.astro can show who is signed in. The answer is about
 * the caller only, never about anyone else on the whitelist.
 *
 * Viewer-guarded: a guest may see its own address too. The role is
 * derived the same way the guards derive it — ADMIN_EMAIL, then the
 * USER_EMAIL list, case-insensitive — and anything else that holds a
 * verified token is a guest, because the guest list is never pushed to
 * the Pages project (see require-viewer.js).
 */
import { requireViewer } from './_utils/require-viewer.js';
import { getAccessUserEmail } from './_utils/cf-access-email.js';

export function roleFor(env, email) {
  const caller = (email || '').trim().toLowerCase();
  const adminEmail = (env.ADMIN_EMAIL || '').trim().toLowerCase();
  if (adminEmail && caller === adminEmail) return 'admin';

  const userEmails = (env.USER_EMAIL || '')
    .split(',')
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  if (userEmails.includes(caller)) return 'user';

  return 'guest';
}

export async function onRequestGet(context) {
  const { env, request } = context;

  const denial = await requireViewer(env, request);
  if (denial) return denial;

  // Memoised per request, so this reuses the verification the guard just
  // did rather than checking the token a second time.
  const { email } = await getAccessUserEmail(request, env);

  return new Response(JSON.stringify({
    success: true,
    email,
    role: roleFor(env, email),
  }), {
    headers: {
      'Content-Type': 'application/json',
      // Per identity: a shared cache must never hand one person's answer
      // to another.
      'Cache-Control': 'private, no-store',
    },
  });
}
