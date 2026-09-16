#!/usr/bin/env bash
# =============================================================================
# update-from-upstream.sh — move this instance's main to an upstream release
# =============================================================================
# Called by .github/workflows/update-from-upstream.yml, from a checkout of
# this instance's main with full history.
#
# Usage: update-from-upstream.sh <upstream-git-url> <tag> <expected-commit>
#
# <expected-commit> is the commit the caller validated for the release. The
# fetched tag must resolve to it, or nothing is pushed.
#
# Only ever fast-forwards. The instance's main moves to the tag's commit when,
# and only when, the tag's commit contains everything main has:
#
#   main == tag                     -> nothing to do
#   tag already contained in main   -> nothing to do (main is at or past it)
#   main contained in tag           -> push the tag's commit to main
#   no common history               -> refuse: a "Use this template" copy
#   both have their own commits     -> refuse: never merge or rebase for
#                                      the operator
#
# The push is a plain `git push`, never forced, so the remote refuses it as
# well if main moved in the meantime.
#
# Writes to $GITHUB_OUTPUT (when set): moved=true|false, from=<sha>, to=<sha>.
# Exit status: 0 when main is at or past the tag afterwards, 1 otherwise.
# =============================================================================
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "❌ usage: $0 <upstream-git-url> <tag> <expected-commit>" >&2
  exit 1
fi
UPSTREAM_URL="$1"
TAG="$2"
EXPECTED="$3"

# Release tags only. The value ends up in a refspec, so it is checked before
# it is used, not only for tidiness.
if ! [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "❌ '$TAG' is not a release tag (expected vMAJOR.MINOR.PATCH)." >&2
  exit 1
fi

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
  fi
}

CURRENT=$(git rev-parse --verify HEAD)
if ! [[ "$EXPECTED" =~ ^[0-9a-f]{40}$ ]]; then
  echo "❌ '$EXPECTED' is not a full commit SHA." >&2
  exit 1
fi

output from "$CURRENT"
output moved false

if ! git fetch --no-tags --quiet "$UPSTREAM_URL" "refs/tags/$TAG"; then
  echo "❌ Could not fetch $TAG from $UPSTREAM_URL." >&2
  exit 1
fi
TARGET=$(git rev-parse --verify "FETCH_HEAD^{commit}")
output to "$TARGET"

if [ "$TARGET" != "$EXPECTED" ]; then
  echo "❌ $TAG resolves to $TARGET, but the release was validated at $EXPECTED." >&2
  echo "   The tag moved during this run. Nothing was pushed." >&2
  exit 1
fi

short() { git rev-parse --short "$1"; }

if [ "$CURRENT" = "$TARGET" ]; then
  echo "✅ main is already at $TAG ($(short "$TARGET")). Nothing to do."
  exit 0
fi

if git merge-base --is-ancestor "$TARGET" "$CURRENT"; then
  echo "✅ main ($(short "$CURRENT")) already contains $TAG ($(short "$TARGET")). Nothing to do."
  exit 0
fi

if ! git merge-base "$CURRENT" "$TARGET" >/dev/null; then
  echo "❌ main and $TAG share no history." >&2
  echo "   This is what a repository created with \"Use this template\" looks like:" >&2
  echo "   GitHub starts such a copy with a single new commit. It has to adopt the" >&2
  echo "   upstream history once before it can be updated. See 'Updating to a new" >&2
  echo "   release' in docs/admin-guides/setup-guide.md." >&2
  exit 1
fi

if ! git merge-base --is-ancestor "$CURRENT" "$TARGET"; then
  echo "❌ main has commits that $TAG does not contain, so it cannot be fast-forwarded." >&2
  echo "   This workflow never merges or rebases on your behalf. Commits on main" >&2
  echo "   that are not in upstream:" >&2
  git log --oneline "$TARGET..$CURRENT" | head -20 >&2
  exit 1
fi

echo "→ Fast-forwarding main: $(short "$CURRENT") -> $(short "$TARGET") ($TAG)"
if ! git push origin "$TARGET:refs/heads/main"; then
  echo "❌ The push was refused. main is unchanged." >&2
  echo "   Either main moved during this run, or the token cannot write to" >&2
  echo "   .github/workflows/ — see UPSTREAM_UPDATE_TOKEN in docs/admin-guides/setup-guide.md." >&2
  exit 1
fi
output moved true
echo "✅ main is now at $TAG ($(short "$TARGET"))."
