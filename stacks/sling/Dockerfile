# =============================================================================
# Sling - multi-arch build
# =============================================================================
# The official slingdata/sling image does not cover every architecture we
# need, so the binary is fetched from the upstream GitHub release, which
# publishes both linux/amd64 and linux/arm64. Which one is fetched follows
# from the build platform instead of being hardcoded.
#
# It used to be hardcoded to arm64, written when the project ran on Hetzner
# ARM (cax31). The default moved to x86 in #525 and this file did not
# follow. That failed quietly rather than loudly: curl and tar will happily
# place an arm64 binary into an amd64 image, so the BUILD succeeds and only
# the first invocation fails with "exec format error". compose-runner treats
# a per-stack failure as a warning and continues the deploy, so the stack
# was unusable without anything going red.
#
# The `sling --version` smoke test at the end of the install closes that
# gap: an architecture mismatch now fails the image build, where it is
# obvious, instead of surfacing later as an unhealthy container.
# =============================================================================

FROM debian:bookworm-slim

# NOT a single source of truth — the version is repeated in six places
# and an upgrade has to touch all of them together:
#
#   stacks/sling/Dockerfile          this ARG (which binary is downloaded)
#   stacks/sling/docker-compose.yml  the image tag
#   services.yaml                    the image field
#   docs/stacks/overview.md          twice: the custom-image paragraph
#                                    and the stack table row
#   docs/stacks/README.md            the image-version table
#
# Editing only this ARG fetches a different binary while the image tag
# and all the metadata keep advertising the old version. The ARG earns
# its place by removing the four repetitions that used to sit inside the
# download URLs below, not by centralising the version project-wide.
ARG SLING_VERSION=1.5.13

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install the Sling binary for this build's architecture.
#
# The download KEEPS its upstream filename on purpose. Each release ships a
# checksum file naming exactly one artefact (`sling_linux_<arch>.tar.gz`),
# so renaming the download would leave `sha256sum -c` with no line it can
# match. The tempting workaround, `--ignore-missing`, is wrong here: it
# turns "the file I downloaded was never checked" into a pass, which is
# strictly worse than no checksum step at all because it looks like one.
# Keeping the name means the plain check verifies the artefact it just got.
#
# `curl -f` so an HTTP error fails here rather than saving an error page
# that only fails later, somewhere less obvious.
RUN set -eux; \
    DPKG_ARCH="$(dpkg --print-architecture)"; \
    case "$DPKG_ARCH" in \
        amd64) SLING_ARCH=amd64 ;; \
        arm64) SLING_ARCH=arm64 ;; \
        *) echo "Unsupported architecture: $DPKG_ARCH" >&2; exit 1 ;; \
    esac; \
    BASE="https://github.com/slingdata-io/sling-cli/releases/download/v${SLING_VERSION}"; \
    cd /tmp; \
    curl -fsSL -o "sling_linux_${SLING_ARCH}.tar.gz" "${BASE}/sling_linux_${SLING_ARCH}.tar.gz"; \
    curl -fsSL -o checksums.txt "${BASE}/linux.${SLING_ARCH}.checksums.txt"; \
    sha256sum -c checksums.txt; \
    tar xzf "sling_linux_${SLING_ARCH}.tar.gz" -C /usr/local/bin; \
    chmod +x /usr/local/bin/sling; \
    rm -f "sling_linux_${SLING_ARCH}.tar.gz" checksums.txt; \
    sling --version

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Keep container running for CLI access
CMD ["sleep", "infinity"]
