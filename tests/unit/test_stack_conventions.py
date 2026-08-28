"""Repo-convention tests, parametrised over every stack.

The conventions these assert are written down in CLAUDE.md and
``.github/copilot-instructions.md``, where they have drifted more than
once — a count that went stale, a `core` service that changed name during
the Forgejo migration, a claim about pinning that the table below it
contradicted. Prose cannot be executed; this can.

Covers, per stack directory under ``stacks/``:

- an entry exists in ``services.yaml``
- ``docs/stacks/<name>.md`` exists
- the image tag is pinned, outside an explicit allow-list
- ``public: true`` only where deliberately public
- ``tcp_ports`` only where an external TCP client genuinely needs it
- a service with no authentication of its own never has ``tcp_ports``

Plus two repo-wide checks that are not per-stack:

- every ``support_images`` key is unique across ``services.yaml``
- every image key derives the ``IMAGE_*`` variable its compose file reads

The allow-lists below are deliberately explicit rather than derived. A
derived list would pass whatever the repo currently does, which is the
opposite of a convention test: adding the tenth ``:latest`` image or the
thirteenth open port should require editing this file and saying why.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STACKS_DIR = REPO_ROOT / "stacks"
DOCS_DIR = REPO_ROOT / "docs" / "stacks"


# ---------------------------------------------------------------------------
# Allow-lists — each entry is a decision, not an observation
# ---------------------------------------------------------------------------

# Presentation-layer and dev tools that keep nothing beyond a cache, plus two
# viewers over another system's state. A moving tag costs nothing here because
# there is no data to meet a changed image. Anything that stores state belongs
# in neither this list nor a floating tag.
LATEST_ALLOWED = {
    "adminer",
    "code-server",
    "drawio",
    "evidence",
    "excalidraw",
    "it-tools",
    "kafka-ui",  # viewer over Kafka; holds nothing itself
    "s3manager",  # viewer over object storage; likewise
    "wetty",
}

# The only service reachable without Cloudflare Access. It exists so that
# `git clone` over HTTPS works from external CI, which an Access email-OTP
# prompt makes impossible.
PUBLIC_ALLOWED = {"git-proxy"}

# A `tcp_ports` entry opens a Hetzner firewall rule, which is the only thing
# that makes a service reachable from outside the tunnel — `hcloud_firewall.main`
# ships with no inbound rules at all. Publishing a Docker port does NOT do
# this; that is how cloudflared reaches a service on localhost and is the
# normal case for 73 of the stacks.
#
# Each entry here is a protocol that genuinely cannot go through an HTTPS
# tunnel: Postgres wire, the Kafka protocol, S3 SDK clients, SFTP.
TCP_PORTS_ALLOWED = {
    "clickhouse",
    "garage",
    "lakefs",
    "minio",
    "pg-ducklake",
    "postgres",
    "redpanda",
    "redpanda-connect",
    "risingwave",
    "rustfs",
    "seaweedfs-filer",
    "sftpgo",
}

# Services whose UI has no login of its own — Cloudflare Access at the edge is
# the entire authentication story. Opening a port for one of these would put
# an unauthenticated interface on the public internet, so they must never
# appear in TCP_PORTS_ALLOWED. The check below enforces exactly that overlap.
NO_OWN_AUTH = {
    "lakekeeper",
    "marquez",
    "questdb",  # the console has none; its Postgres wire protocol does
    "unity-catalog",
}

# services.yaml entries that share another stack's directory rather than
# having one of their own. Both are SeaweedFS components split out so they can
# be enabled and given firewall rules independently.
SHARED_DIRECTORY = {
    "seaweedfs-filer": "seaweedfs",
    "seaweedfs-manager": "seaweedfs",
}

# Stacks whose documentation file is not named after the service key.
DOC_NAME_OVERRIDES = {
    "woodpecker": "woodpecker-ci",
    # Both are components of the SeaweedFS stack and are documented on its
    # page rather than on one of their own.
    "seaweedfs-filer": "seaweedfs",
    "seaweedfs-manager": "seaweedfs",
}

# Pre-existing collisions, tracked in #715. Nineteen stacks use the key
# `postgres` and two use `redis`, so all of them collapse into a single
# IMAGE_POSTGRES / IMAGE_REDIS. Listed here so the test passes today while
# still failing for any NEW collision — removing an entry is how #715 gets
# closed.
# Keyed by (key, owner), not by key alone. Exempting the key would let a
# NEW stack adopt `postgres` and pass — the opposite of what the comment
# above promises. Adding one now fails until it is listed here, which is a
# decision someone has to make deliberately.
KNOWN_SUPPORT_IMAGE_COLLISIONS: set[tuple[str, str]] = {
    (key, owner)
    for key, owners in {
        "postgres": (
            "dagster",
            "gitea",
            "hedgedoc",
            "hoppscotch",
            "infisical",
            "lakefs",
            "lakekeeper",
            "kestra",
            "litellm",
            "mage",
            "meltano",
            "metabase",
            "superset",
            "n8n",
            "nocodb",
            "openmetadata",
            "prefect",
            "soda",
            "windmill",
        ),
        "redis": ("infisical", "superset"),
    }.items()
    for owner in owners
}

COLLIDING_KEYS = {key for key, _ in KNOWN_SUPPORT_IMAGE_COLLISIONS}

# A tag is floating when any dash- or dot-separated component is a moving
# label. `:latest` is the obvious one; `3-latest` and `latest-sql-spark`
# are not caught by a suffix check and were passing as pinned, and `18-main`
# tracks a branch. A major pin like `17-alpine` or `v24.3` is deliberate
# policy and not floating.
FLOATING_COMPONENTS = {"latest", "main", "nightly", "edge", "dev"}

# Stateful stacks that track a moving tag because upstream publishes nothing
# narrower. Already marked `Rolling ⚠️` in docs/stacks/README.md; listed here
# so the test agrees with the table rather than contradicting it.
ROLLING_ALLOWED = {
    "marimo",  # nexus-marimo:latest-sql-spark — locally built, no version tags
    "pg-ducklake",  # pgducklake/pgducklake:18-main
    "prefect",  # prefecthq/prefect:3-latest
}

# Image keys whose IMAGE_* variable no compose file reads, so a version bump
# in services.yaml never reaches the container. Same defect as #715 and
# tracked there, but a wider set than the shared `postgres` key, with three
# distinct causes:
#
#   - reversed naming: the compose reads ${CLOUDBEAVER_IMAGE} while the
#     deploy emits IMAGE_CLOUDBEAVER (cloudbeaver, redpanda,
#     redpanda-console)
#   - a differently-named variable: woodpecker's compose reads
#     IMAGE_WOODPECKER_SERVER, the services.yaml key is `woodpecker`
#   - support images the compose simply hardcodes (flink-taskmanager,
#     ingestion, elasticsearch, wikijs-postgres, lsp)
#
# Two of these have already diverged in practice, which is what the defect
# looks like when it bites: services.yaml says redpanda v24.3 and
# redpanda-console v2.8, while the compose defaults that actually run are
# v24.3.1 and v2.8.0. The pinned version in the docs is not the deployed one.
#
# Entries are (stack, image-key). Removing one is how the fix gets verified.
KNOWN_UNREAD_IMAGE_VARS = {
    ("cloudbeaver", "cloudbeaver"),
    ("flink", "flink-taskmanager"),
    ("openmetadata", "ingestion"),
    ("openmetadata", "elasticsearch"),
    ("redpanda", "redpanda"),
    ("redpanda-console", "redpanda-console"),
    ("wikijs", "wikijs-postgres"),
    ("windmill", "lsp"),
    ("woodpecker", "woodpecker"),
    # Both declare their own image in services.yaml, so the deploy emits
    # IMAGE_SEAWEEDFS_FILER and IMAGE_SEAWEEDFS_MANAGER — but the shared
    # stacks/seaweedfs/docker-compose.yml reads only ${IMAGE_SEAWEEDFS}.
    ("seaweedfs-filer", "seaweedfs-filer"),
    ("seaweedfs-manager", "seaweedfs-manager"),
}

# Support images still on :latest. Each is a UI or sidecar rather than a
# store, which is why they were left — but unlike the primary-image
# allow-list these were never a stated decision, so they are recorded as
# debt rather than blessed.
# Stacks with no container named exactly like their services.yaml key.
# compose_runner verifies a stack started with
# `docker ps --format '{{.Names}}' | grep -qFx -- "$svc"`, which is
# fixed-string and line-exact, so a mismatch makes the stack report as
# failed while running perfectly. Tracked in #726.
KNOWN_CONTAINER_NAME_MISMATCH = {"woodpecker"}

KNOWN_UNPINNED_SUPPORT_IMAGES = {
    ("dify", "dify-ssrf-proxy"),
    ("garage", "webui"),
    ("windmill", "lsp"),
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load_services() -> dict[str, Any]:
    with (REPO_ROOT / "services.yaml").open() as fh:
        return dict(yaml.safe_load(fh)["services"])


SERVICES: dict[str, Any] = _load_services()
STACK_DIRS: list[str] = sorted(p.parent.name for p in STACKS_DIR.glob("*/docker-compose.yml"))


@pytest.fixture(scope="module")
def services() -> dict[str, Any]:
    return SERVICES


def _is_floating(image: str) -> bool:
    """A tag whose components include a moving label.

    Checked component-wise rather than by suffix: `endswith(":latest")`
    misses `3-latest` and `latest-sql-spark`, both of which move. A digest
    reference is never floating; a major pin like `17-alpine` is deliberate
    policy and not a moving tag.
    """
    if "@" in image:  # digest-pinned
        return False

    # No tag at all is NOT pinned: Docker resolves a bare reference as
    # `:latest`, so `redis` and `redis:latest` pull the same moving image.
    # Splitting on the last path segment avoids reading the colon in a
    # registry host with a port (`registry:5000/img`) as a tag separator.
    tail = image.rsplit("/", 1)[-1]
    if ":" not in tail:
        return True

    tag = tail.rsplit(":", 1)[-1]
    return any(part in FLOATING_COMPONENTS for part in re.split(r"[-.]", tag))


def _image_env_var(key: str) -> str:
    """Mirror the orchestrator's derivation exactly.

    `orchestrator.py` renders `"IMAGE_" + key.replace("-", "_").upper()`.
    Duplicating it here rather than importing keeps the test honest about
    what it is asserting: that the compose file reads the name the deploy
    actually emits, not the name a helper happens to produce.
    """
    return "IMAGE_" + key.replace("-", "_").upper()


# ---------------------------------------------------------------------------
# Per-stack checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stack", STACK_DIRS)
def test_stack_has_services_yaml_entry(stack: str, services: dict[str, Any]) -> None:
    """Every stack directory is registered.

    An unregistered stack is invisible to the Control Plane and to the
    deploy: the compose file sits there and is never started.
    """
    assert stack in services, (
        f"stacks/{stack}/ has no entry in services.yaml — it would never be deployed"
    )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_service_has_documentation(name: str) -> None:
    """Every service has a reference doc.

    Checked over services.yaml rather than directories so that entries
    sharing a directory (the SeaweedFS components) still need their own page
    or an explicit override.
    """
    doc_name = DOC_NAME_OVERRIDES.get(name, name)
    doc = DOCS_DIR / f"{doc_name}.md"
    assert doc.exists(), (
        f"{doc.relative_to(REPO_ROOT)} is missing. Add it, or record a "
        f"DOC_NAME_OVERRIDES entry if the file is deliberately named differently."
    )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_image_tag_is_pinned(name: str, services: dict[str, Any]) -> None:
    """No stateful stack tracks a floating tag.

    A `:latest` that moved between two spin-ups would meet data written by
    the previous one. The allow-list holds tools that keep nothing.
    """
    image = str(services[name].get("image", ""))
    if not image:
        pytest.skip(f"{name} declares no image")
    if _is_floating(image):
        assert name in LATEST_ALLOWED or name in ROLLING_ALLOWED, (
            f"{name} tracks the floating tag {image!r}. Pin it, or add it to "
            f"LATEST_ALLOWED (holds no state) or ROLLING_ALLOWED (upstream "
            f"publishes nothing narrower) with a comment saying which."
        )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_support_images_are_pinned(name: str, services: dict[str, Any]) -> None:
    """Support images follow the same rule as the primary image.

    They are easy to forget precisely because they are not the headline of
    the stack — the database behind an app is exactly the thing that must
    not move.
    """
    for key, image in (services[name].get("support_images") or {}).items():
        if (name, key) in KNOWN_UNPINNED_SUPPORT_IMAGES:
            continue
        assert not _is_floating(str(image)), (
            f"{name}.support_images.{key} tracks the floating tag {image!r} — pin "
            f"it. Support images are usually the stateful half of a stack."
        )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_public_only_where_intended(name: str, services: dict[str, Any]) -> None:
    """`public: true` skips Cloudflare Access entirely."""
    if services[name].get("public"):
        assert name in PUBLIC_ALLOWED, (
            f"{name} is public: true, which removes the Access gate. Only "
            f"{sorted(PUBLIC_ALLOWED)} are meant to be."
        )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_tcp_ports_only_where_intended(name: str, services: dict[str, Any]) -> None:
    """`tcp_ports` opens the Hetzner firewall.

    Note this is about tcp_ports, not about a `ports:` line in the compose
    file. Publishing a Docker port is how cloudflared reaches a service and
    is unremarkable; opening the firewall is the decision worth reviewing.
    """
    if services[name].get("tcp_ports"):
        assert name in TCP_PORTS_ALLOWED, (
            f"{name} declares tcp_ports, which creates a Hetzner firewall rule "
            f"and makes it reachable outside the tunnel. Add it to "
            f"TCP_PORTS_ALLOWED only if the protocol genuinely cannot go "
            f"through HTTPS."
        )


@pytest.mark.parametrize("name", sorted(NO_OWN_AUTH))
def test_services_without_auth_are_never_exposed(name: str, services: dict[str, Any]) -> None:
    """A service with no login of its own must stay behind Access.

    These rely entirely on Cloudflare Access. A firewall rule would put an
    unauthenticated interface on the public internet — the failure mode is
    silent, because the service starts and works exactly as before.
    """
    if name not in services:
        pytest.skip(f"{name} is not registered")
    assert not services[name].get("tcp_ports"), (
        f"{name} has no authentication of its own and must not declare "
        f"tcp_ports. Expose an authenticating port instead, or give it a login."
    )
    assert not services[name].get("public"), (
        f"{name} has no authentication of its own and must not be public."
    )


@pytest.mark.parametrize("stack", STACK_DIRS)
def test_compose_reads_the_image_variables_the_deploy_emits(
    stack: str, services: dict[str, Any]
) -> None:
    """Every image key derives a variable the compose file actually reads.

    `tofu output image_versions` merges all images into one flat map and the
    orchestrator renders each key as IMAGE_<KEY>. A key whose variable the
    compose file does not read means a version bump in services.yaml never
    reaches the container, while the fallback quietly stays authoritative —
    the change appears to have been made and was not.
    """
    if stack not in services:
        pytest.skip(f"{stack} has no services.yaml entry")

    compose = (STACKS_DIR / stack / "docker-compose.yml").read_text()

    # Services that share this directory count too. seaweedfs-filer and
    # seaweedfs-manager declare their own image, so the deploy emits
    # IMAGE_SEAWEEDFS_FILER and IMAGE_SEAWEEDFS_MANAGER — but they have no
    # directory of their own, so parametrising over directories alone would
    # never reach them and their KNOWN_UNREAD_IMAGE_VARS entries would sit
    # there unverified.
    owners = [stack] + [n for n, shared in SHARED_DIRECTORY.items() if shared == stack]

    keys: list[tuple[str, str]] = []
    for owner in owners:
        entry = services.get(owner, {})
        if entry.get("image"):
            keys.append((owner, owner))
        keys += [(owner, k) for k in (entry.get("support_images") or {})]

    for owner, key in keys:
        if key in COLLIDING_KEYS or (owner, key) in KNOWN_UNREAD_IMAGE_VARS:
            continue  # tracked in #715
        var = _image_env_var(key)

        # Any valid reference form counts as reading it — ${VAR}, ${VAR:-x},
        # ${VAR:?x}, ${VAR-x}. The question this test asks is whether the
        # compose reads the variable, not which interpolation syntax it uses.
        assert re.search(rf"\$\{{{var}[}}:?-]", compose), (
            f"stacks/{stack}/docker-compose.yml does not read ${{{var}}}, which is "
            f"what the deploy emits for the '{key}' image. A version bump in "
            f"services.yaml would silently not reach the container."
        )

        # Separately: the fallback must exist, so the compose still starts
        # standalone when the deploy has not rendered a value.
        assert f"${{{var}:-" in compose, (
            f"stacks/{stack}/docker-compose.yml reads ${{{var}}} without a default. "
            f"Use ${{{var}:-<image>}} so the stack starts outside the deploy."
        )


@pytest.mark.parametrize("stack", STACK_DIRS)
def test_a_container_is_named_after_the_service(stack: str, services: dict[str, Any]) -> None:
    """The deploy proves a stack started by looking for this exact name.

    `compose_runner` collects the services.yaml key and checks it against
    `docker ps --format '{{.Names}}'` with `grep -qFx` — fixed-string and
    line-exact. A stack whose containers are all named something else
    reports "compose up succeeded but container not in 'docker ps'" on
    every deploy, while running perfectly. The failure is loud in the log
    and completely misleading, which is why it needs a test rather than a
    convention.
    """
    if stack in KNOWN_CONTAINER_NAME_MISMATCH:
        pytest.skip(f"{stack} is a known mismatch, tracked in #726")

    compose = yaml.safe_load((STACKS_DIR / stack / "docker-compose.yml").read_text())
    names = {
        svc.get("container_name")
        for svc in (compose.get("services") or {}).values()
        if svc.get("container_name")
    }
    assert stack in names, (
        f"stacks/{stack}/ has no container named '{stack}'. Found: {sorted(names)}. "
        f"compose_runner greps `docker ps` for the services.yaml key line-exact, "
        f"so this stack would report as failed on every deploy while running."
    )


# ---------------------------------------------------------------------------
# Repo-wide checks
# ---------------------------------------------------------------------------


def test_support_image_keys_are_unique(services: dict[str, Any]) -> None:
    """No two stacks may claim the same support_images key.

    They are merged into one flat map, so a shared key means one image wins
    and the others silently take its value.
    """
    seen: dict[str, list[str]] = {}
    for name, entry in services.items():
        for key in entry.get("support_images") or {}:
            seen.setdefault(key, []).append(name)

    collisions = {
        key: sorted(o for o in owners if (key, o) not in KNOWN_SUPPORT_IMAGE_COLLISIONS)
        for key, owners in seen.items()
        if len(owners) > 1
    }
    collisions = {k: v for k, v in collisions.items() if v}
    assert not collisions, (
        f"support_images keys claimed by more than one stack: {collisions}. "
        f"Prefix them with the stack name, as dify-postgres and forgejo-postgres do."
    )


def test_every_services_entry_has_a_stack_directory(services: dict[str, Any]) -> None:
    """Each entry either owns a directory or shares a declared one."""
    for name in services:
        if name in SHARED_DIRECTORY:
            shared = SHARED_DIRECTORY[name]
            assert (STACKS_DIR / shared / "docker-compose.yml").exists(), (
                f"{name} is declared as sharing stacks/{shared}/, which does not exist"
            )
            continue
        assert name in STACK_DIRS, (
            f"services.yaml declares '{name}' but stacks/{name}/docker-compose.yml "
            f"does not exist. Add it to SHARED_DIRECTORY if it deliberately lives "
            f"inside another stack."
        )


def test_ports_are_unique_across_stacks(services: dict[str, Any]) -> None:
    """Two stacks binding the same host port cannot both start.

    Known exceptions are pairs that are alternatives to each other or
    components of one stack, never enabled in a conflicting combination.
    """
    known_shared = {
        frozenset({"pg-ducklake", "postgres"}),  # alternative Postgres flavours
        frozenset({"seaweedfs", "seaweedfs-filer"}),  # one stack, split entries
    }

    by_port: dict[int, list[str]] = {}
    for name, entry in services.items():
        port = entry.get("port")
        if port:
            by_port.setdefault(int(port), []).append(name)

    unexpected = {
        port: sorted(names)
        for port, names in by_port.items()
        if len(names) > 1 and frozenset(names) not in known_shared
    }
    assert not unexpected, f"host port claimed by more than one stack: {unexpected}"


def test_core_services_are_the_documented_four(services: dict[str, Any]) -> None:
    """`core: true` means always deployed and not disableable.

    Pinned because the set is small, load-bearing, and has changed silently
    before — Gitea held a place here until the Forgejo migration took it.
    """
    core = {name for name, entry in services.items() if entry.get("core")}
    assert core == {"forgejo", "grafana", "infisical", "portainer"}, (
        f"core services changed to {sorted(core)}. That is a deliberate decision; "
        f"update this test and the docs together."
    )
