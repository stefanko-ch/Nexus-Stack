#!/usr/bin/env bash
# =============================================================================
# install-tool.sh — install a pinned tool that a job image may not have
# =============================================================================
# The lifecycle workflows were written for GitHub's `ubuntu-latest`, which
# ships jq, the AWS CLI and sudo. A Conductor tenant fork runs them on a
# Forgejo runner whose job image is `node:22-bookworm`, which has none of
# these (#884). Each job therefore installs what it needs with this script,
# the way install-opentofu.sh installs OpenTofu: a pinned version, a pinned
# checksum, a directory under $RUNNER_TEMP, and no sudo. It works the same on
# both runners.
#
# Usage: install-tool.sh <jq|cloudflared|awscli>
#
# Installs into $RUNNER_TEMP/tools/<tool>-<version>-<arch>/ and, when
# GITHUB_PATH is set, puts that directory on PATH for the following steps.
#
# Where the checksums come from (checked 2026-09-17, amd64 and arm64):
#   jq 1.8.2           the release's sha256sum.txt, equal to the asset digest
#                      GitHub records for the release, and to the download
#   cloudflared 2026.9.1
#                      the checksums in the release notes, equal to GitHub's
#                      asset digest, and to the download
#   AWS CLI 2.36.47    the zip's PGP signature verified against the key the
#                      AWS CLI install guide publishes (fingerprint FB5D B77F
#                      D5C1 18B8 0511 ADA8 A631 0ACC 4672 475C) -> "Good
#                      signature"; the same signature on the other
#                      architecture's zip -> "BAD signature"
#
# To move a tool to another version: repeat that check, then replace its
# version and both checksums below. Replace, do not add.
# =============================================================================
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "❌ usage: install-tool.sh <jq|cloudflared|awscli>" >&2
  exit 1
fi
TOOL="$1"

if [ "$(uname -s)" != "Linux" ]; then
  echo "❌ install-tool.sh supports Linux runners only (got $(uname -s))." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64 | amd64) ARCH=amd64 ;;
  aarch64 | arm64) ARCH=arm64 ;;
  *)
    echo "❌ No $TOOL build pinned for architecture $(uname -m)." >&2
    exit 1
    ;;
esac

# The pins. VERSION, the download URL, its checksum per architecture, the
# command the tool installs, and the text its version output must contain.
case "$TOOL/$ARCH" in
  jq/amd64 | jq/arm64)
    VERSION="1.8.2"
    FILE="jq-linux-$ARCH"
    URL="https://github.com/jqlang/jq/releases/download/jq-$VERSION/$FILE"
    case "$ARCH" in
      amd64) SHA256="b1c22172dd303f3be49e935aa56aa48a8b7a46e0bc838b4997d3bb451495870f" ;;
      arm64) SHA256="8b85c817833814ddca00a144c33705546355afccf0cf39b188f3cdb48b852309" ;;
    esac
    COMMAND="jq"
    EXPECT="jq-$VERSION"
    ;;
  cloudflared/amd64 | cloudflared/arm64)
    VERSION="2026.9.1"
    FILE="cloudflared-linux-$ARCH"
    URL="https://github.com/cloudflare/cloudflared/releases/download/$VERSION/$FILE"
    case "$ARCH" in
      amd64) SHA256="03f1f25d1cc93b9ad6c60569d44060bc4f17ed97075760ed8cfca4b12dcd68cc" ;;
      arm64) SHA256="3d97437c71848bd8df68041e12436b484a661d95073ea1937f01a845ce88faa3" ;;
    esac
    COMMAND="cloudflared"
    EXPECT="cloudflared version $VERSION "
    ;;
  awscli/amd64 | awscli/arm64)
    VERSION="2.36.47"
    case "$ARCH" in
      amd64) FILE="awscli-exe-linux-x86_64-$VERSION.zip"
             SHA256="44ab93f1c6e90e0a34dfe5da6b798d99f2f6b41825e97022b3d409d93a65c615" ;;
      arm64) FILE="awscli-exe-linux-aarch64-$VERSION.zip"
             SHA256="118ef53b6f5c652471fd299af01c058901c1a53db69c6b71a7bf3ebd93590969" ;;
    esac
    URL="https://awscli.amazonaws.com/$FILE"
    COMMAND="aws"
    EXPECT="aws-cli/$VERSION "
    ;;
  *)
    echo "❌ Unknown tool '$TOOL' (expected jq, cloudflared or awscli)." >&2
    exit 1
    ;;
esac

DEST="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tools/$TOOL-$VERSION-$ARCH"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if ! curl -fsSL --retry 3 --retry-delay 2 -o "$WORK/$FILE" "$URL"; then
  echo "❌ Could not download $URL" >&2
  exit 1
fi

# `sha256sum` prints "<hash>  <file>"; the expansion keeps only the hash
# without a pipe (#883).
if ! SUM=$(sha256sum "$WORK/$FILE"); then
  echo "❌ Could not compute the checksum of $FILE." >&2
  exit 1
fi
ACTUAL=${SUM%% *}
if [ "$ACTUAL" != "$SHA256" ]; then
  echo "❌ Checksum mismatch for $FILE — refusing to install it." >&2
  echo "   expected $SHA256" >&2
  echo "   got      $ACTUAL" >&2
  exit 1
fi

mkdir -p "$DEST"
case "$TOOL" in
  awscli)
    # The official installer, without root: it takes an install directory
    # and a bin directory, both under $DEST. unzip is in both job images;
    # Python's zipfile is the fallback, and python3 is in both as well.
    mkdir -p "$WORK/extract"
    if command -v unzip >/dev/null; then
      unzip -q "$WORK/$FILE" -d "$WORK/extract"
    else
      python3 -m zipfile -e "$WORK/$FILE" "$WORK/extract"
      chmod -R u+x "$WORK/extract/aws"
    fi
    "$WORK/extract/aws/install" --install-dir "$DEST/aws-cli" --bin-dir "$DEST/bin" --update >/dev/null
    BIN_DIR="$DEST/bin"
    ;;
  *)
    install -m 0755 "$WORK/$FILE" "$DEST/$COMMAND"
    BIN_DIR="$DEST"
    ;;
esac

# Read back what was installed. Whole output first, no pipe (#883).
if ! INSTALLED=$("$BIN_DIR/$COMMAND" --version 2>&1); then
  echo "❌ $BIN_DIR/$COMMAND --version failed: ${INSTALLED:-(no output)}" >&2
  exit 1
fi
INSTALLED=${INSTALLED%%$'\n'*}
case "$INSTALLED" in
  "$EXPECT"*) ;;
  *)
    echo "❌ Installed $COMMAND reports '$INSTALLED', expected it to start with '$EXPECT'." >&2
    exit 1
    ;;
esac

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$BIN_DIR" >> "$GITHUB_PATH"
fi
echo "✅ $INSTALLED installed at $BIN_DIR"
