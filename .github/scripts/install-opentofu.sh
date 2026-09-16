#!/usr/bin/env bash
# =============================================================================
# install-opentofu.sh — install the pinned OpenTofu without a marketplace action
# =============================================================================
# Every workflow that runs `tofu` calls this instead of
# `opentofu/setup-opentofu`, because that action cannot be resolved on a
# Forgejo runner (#872). Forgejo resolves a bare `uses: owner/repo@ref` against
# DEFAULT_ACTIONS_URL, which the forgejo stack pins to https://data.forgejo.org,
# and data.forgejo.org does not mirror `opentofu/setup-opentofu`. A Conductor
# tenant fork therefore stopped at its first `tofu` step. A plain script runs
# the same on GitHub Actions and on Forgejo.
#
# The version and its checksums live here and nowhere else. Callers pass no
# version, so every workflow installs the same one — which tofu-checks.yaml
# depends on: a checker on a different version than the applier can pass what
# the applier rejects.
#
# The checksums are pinned, not fetched. Downloading SHA256SUMS next to the
# archive would catch a broken download but not a replaced one, since both
# would come from the same place. The values below were taken from
# tofu_1.10.0_SHA256SUMS after verifying that file with cosign, the way
# https://opentofu.org/docs/intro/install/standalone/ documents:
#
#   cosign verify-blob \
#     --certificate-identity "https://github.com/opentofu/opentofu/.github/workflows/release.yml@refs/heads/v1.10" \
#     --certificate-oidc-issuer https://token.actions.githubusercontent.com \
#     --signature tofu_1.10.0_SHA256SUMS.sig --certificate tofu_1.10.0_SHA256SUMS.pem \
#     tofu_1.10.0_SHA256SUMS
#   -> Verified OK   (and the same command with a wrong identity is refused)
#
# To move to another version: run that check for its SHA256SUMS, add its two
# `linux_*.tar.gz` lines to expected_sha256, and change PINNED_VERSION.
#
# The .tar.gz rather than the .zip: `tar` is in every runner image, including
# the Forgejo runner's node:22-bookworm; `unzip` is not a given.
#
# Usage: install-opentofu.sh
# Installs `tofu` and, when GITHUB_PATH is set, puts it on PATH for the
# following steps. Both GitHub Actions and the Forgejo runner honour
# GITHUB_PATH.
# =============================================================================
set -euo pipefail

PINNED_VERSION="1.10.0"

expected_sha256() {
  case "$1/$2" in
    1.10.0/amd64) echo "9f4e7473608f55bbc8eb64178228569a14af6463f5332607deecdf3f9bf31e8b" ;;
    1.10.0/arm64) echo "df4d875ab635390caf54fb07f3e2b5fdd2c88b06bf04f601da1df63bb0da7e95" ;;
    *) return 1 ;;
  esac
}

if [ "$#" -ne 0 ]; then
  echo "❌ install-opentofu.sh takes no arguments; the version is pinned inside it ($PINNED_VERSION)." >&2
  exit 1
fi
VERSION="$PINNED_VERSION"

if [ "$(uname -s)" != "Linux" ]; then
  echo "❌ install-opentofu.sh supports Linux runners only (got $(uname -s))." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64 | amd64) ARCH=amd64 ;;
  aarch64 | arm64) ARCH=arm64 ;;
  *)
    echo "❌ No OpenTofu build pinned for architecture $(uname -m)." >&2
    exit 1
    ;;
esac

if ! SHA256=$(expected_sha256 "$VERSION" "$ARCH"); then
  echo "❌ No checksum pinned for OpenTofu $VERSION on linux_$ARCH — see the header of $0." >&2
  exit 1
fi

ARCHIVE="tofu_${VERSION}_linux_${ARCH}.tar.gz"
URL="https://github.com/opentofu/opentofu/releases/download/v${VERSION}/${ARCHIVE}"
DEST="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/opentofu-${VERSION}-${ARCH}"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if ! curl -fsSL --retry 3 --retry-delay 2 -o "$WORK/$ARCHIVE" "$URL"; then
  echo "❌ Could not download $URL" >&2
  exit 1
fi

ACTUAL=$(sha256sum "$WORK/$ARCHIVE" | cut -d' ' -f1)
if [ "$ACTUAL" != "$SHA256" ]; then
  echo "❌ Checksum mismatch for $ARCHIVE — refusing to install it." >&2
  echo "   expected $SHA256" >&2
  echo "   got      $ACTUAL" >&2
  exit 1
fi

mkdir -p "$WORK/extract"
if ! tar -xzf "$WORK/$ARCHIVE" -C "$WORK/extract" tofu; then
  echo "❌ $ARCHIVE passed its checksum but did not contain a tofu binary." >&2
  exit 1
fi
mkdir -p "$DEST"
install -m 0755 "$WORK/extract/tofu" "$DEST/tofu"

# Read back what was installed rather than assuming it.
INSTALLED=$("$DEST/tofu" version | head -n 1)
if [ "$INSTALLED" != "OpenTofu v$VERSION" ]; then
  echo "❌ Installed binary reports '$INSTALLED', expected 'OpenTofu v$VERSION'." >&2
  exit 1
fi

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$DEST" >> "$GITHUB_PATH"
fi
echo "✅ $INSTALLED installed at $DEST"
