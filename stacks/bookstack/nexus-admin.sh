#!/usr/bin/with-contenv bash
# shellcheck shell=bash
# =============================================================================
# Replace BookStack's default admin (admin@admin.com / password)
# =============================================================================
# Runs from /custom-cont-init.d after the image's own init has migrated the
# database. On a fresh database it turns the default admin into nexus-admin
# with the stack user's email and BOOKSTACK_ADMIN_PASSWORD. On later starts
# create-admin finds a non-default admin and changes nothing.
#
# The password is answered on stdin (printf is a bash builtin), never passed
# as --password.
#
# A failure stops the container: linuxserver ignores the exit status of
# custom init scripts, so fail() halts s6 itself. BookStack must not come
# up serving admin@admin.com / password. The container then restarts and
# tries again, and keeps failing visibly until the cause is fixed.
# =============================================================================
set -euo pipefail

fail() {
  echo "nexus-admin: ERROR: $* Stopping the container." >&2
  /run/s6/basedir/bin/halt
  exit 1
}

# HOME: tinker (psysh) writes its config there, and /root is not abc's.
artisan() { s6-setuidgid abc env HOME=/tmp php /app/www/artisan "$@"; }

status=0
printf '%s\n' "$BOOKSTACK_ADMIN_PASSWORD" \
  | artisan bookstack:create-admin --initial \
      --email="$BOOKSTACK_ADMIN_EMAIL" --name="nexus-admin" >/dev/null || status=$?
# 0: default admin updated, 2: a non-default admin already exists.
if [[ $status -ne 0 && $status -ne 2 ]]; then
  fail "bookstack:create-admin failed (exit $status)."
fi

# The check reads the values from the environment inside PHP, so neither
# the email nor the password appears in an argument list. The $ signs are
# PHP variables, hence the single quotes.
# shellcheck disable=SC2016
result=$(artisan tinker --execute='
  $u = \BookStack\Users\Models\User::where("email", "admin@admin.com")->first();
  if ($u && $u->hasSystemRole("admin")) { echo "DEFAULT"; return; }
  $n = \BookStack\Users\Models\User::where("email", getenv("BOOKSTACK_ADMIN_EMAIL"))->first();
  if (!$n) { echo "MISSING"; return; }
  echo \Illuminate\Support\Facades\Hash::check(getenv("BOOKSTACK_ADMIN_PASSWORD"), $n->password) ? "OK" : "CHANGED";
' 2>/dev/null | tail -n 1)

case "$result" in
  OK) echo "nexus-admin: nexus-admin logs in with the generated password." ;;
  CHANGED)
    if [[ $status -eq 0 ]]; then
      fail "the password just set does not match."
    fi
    echo "nexus-admin: WARNING: the generated password no longer matches -- expected if it was changed in BookStack. Nothing changed." >&2 ;;
  DEFAULT) fail "the default admin@admin.com account is still an admin." ;;
  MISSING)
    # create-admin skipped (exit 2) because another admin exists; the
    # stack user's email may have changed since. Not a default login.
    echo "nexus-admin: WARNING: no user with the stack user's email; another admin exists. Nothing changed." >&2 ;;
  *) fail "could not check the admin account." ;;
esac
