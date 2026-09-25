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
- every ``${IMAGE_*}`` the compose reads is one the deploy actually emits
- a PostgreSQL container writes where its volume is mounted

Plus two repo-wide checks that are not per-stack:

- every ``support_images`` key is unique across ``services.yaml``
- every image key derives the ``IMAGE_*`` variable its compose file reads

The allow-lists below are deliberately explicit rather than derived. A
derived list would pass whatever the repo currently does, which is the
opposite of a convention test: adding the tenth ``:latest`` image or the
thirteenth open port should require editing this file and saying why.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml

from nexus_deploy.compose_runner import (
    _DEFERRED_SERVICES,
    _STACK_PARENTS,
    expand_targets,
)

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
    "mongodb",  # wire protocol; authenticates as nexus-mongodb
    "pg-ducklake",
    "postgres",
    "redpanda",
    "redpanda-connect",
    "risingwave",
    "rustfs",
    "seaweedfs-filer",
    "sftpgo",
    "timescaledb",  # Postgres wire, same as `postgres` and `pg-ducklake`
}

# Services whose UI has no login of its own — Cloudflare Access at the edge is
# the entire authentication story. Opening a port for one of these would put
# an unauthenticated interface on the public internet, so they must never
# appear in TCP_PORTS_ALLOWED. The check below enforces exactly that overlap.
NO_OWN_AUTH = {
    "lakekeeper",
    "marquez",
    "questdb",  # the console has none; its Postgres wire protocol does
    "temporal",  # neither the Web UI nor the gRPC frontend authenticates
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

# Support-image keys claimed by more than one stack. Empty since #715:
# nineteen stacks shared the key `postgres` and two shared `redis`, all of
# them collapsing into a single IMAGE_POSTGRES / IMAGE_REDIS. Each now
# carries its own prefixed key, so there is nothing left to exempt.
#
# Keyed by (key, owner) rather than by key alone, so that re-introducing
# the pattern for one stack cannot be waved through for all of them.
KNOWN_SUPPORT_IMAGE_COLLISIONS: set[tuple[str, str]] = set()


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
# tracked there, but a wider set than the shared `postgres` key. Two causes
# remain, the third having been cleared:
#
#   - reversed naming: the compose reads ${CLOUDBEAVER_IMAGE} while the
#     deploy emits IMAGE_CLOUDBEAVER (cloudbeaver, redpanda,
#     redpanda-console)
#   - support images the compose simply hardcodes (flink-taskmanager,
#     wikijs-postgres)
#
# The third cause -- a compose reading a variable name the deploy never
# emits -- is gone. A sweep of every ${IMAGE_*} reference against
# services.yaml found five: woodpecker, planka, ollama and openmetadata
# twice, all fixed in #738. That direction is now covered by
# test_every_image_variable_a_compose_reads_is_declared rather than by a
# sweep run once by hand, so a new case fails the suite instead of
# quietly using its fallback.
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
    ("redpanda", "redpanda"),
    ("redpanda-console", "redpanda-console"),
    ("wikijs", "wikijs-postgres"),
    # Both declare their own image in services.yaml, so the deploy emits
    # IMAGE_SEAWEEDFS_FILER and IMAGE_SEAWEEDFS_MANAGER — but the shared
    # stacks/seaweedfs/docker-compose.yml reads only ${IMAGE_SEAWEEDFS}.
    ("seaweedfs-filer", "seaweedfs-filer"),
    ("seaweedfs-manager", "seaweedfs-manager"),
}

# Stacks the compose-up verification never looks at, so the exact-name rule
# cannot apply to them. Named for what it is — an exemption from a check —
# rather than for a defect: these stacks may well have a container named
# something other than their key, and for them that is simply not a problem.
#
# Derived from the deploy's own table rather than restated. `expand_targets`
# skips deferred services outright, so they never enter NAMES and never
# reach the `docker ps` grep. Woodpecker is deferred because it needs
# Forgejo OAuth credentials that exist only after the bootstrap pipeline
# has run; `_phase_woodpecker_apply` starts it afterwards with a plain
# `docker compose up -d` and no name check.
#
# Importing the set means the exemption disappears the moment a service
# stops being deferred — which is exactly when the rule starts to matter
# for it again.
NAME_CHECK_EXEMPT = set(_DEFERRED_SERVICES)

# support_images keys that shadow a service's own primary image. The merge
# in tofu/stack/outputs.tf puts support_images LAST, and Terraform's merge()
# lets the later argument win, so such a key does not merely collide -- it
# overrides the service's own image in IMAGE_*.
#
# Empty. `postgres` was fixed by #715; `ollama` was the last one and is
# fixed by giving that stack the primary image its own name implies. The
# services.yaml entry declared open-webui as the `ollama` service's image
# while a support key `ollama` carried the actual Ollama server, so
# IMAGE_OLLAMA resolved to the support value -- correct by accident, and
# IMAGE_OPEN_WEBUI was never emitted at all.
KNOWN_PRIMARY_IMAGE_SHADOWING: set[str] = set()

# Support images still on :latest. Each is a UI or sidecar rather than a
# store, which is why they were left — but unlike the primary-image
# allow-list these were never a stated decision, so they are recorded as
# debt rather than blessed.
KNOWN_UNPINNED_SUPPORT_IMAGES = {
    ("dify", "dify-ssrf-proxy"),
    ("garage", "webui"),
    ("windmill", "windmill-lsp"),
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

    # Only the `image:` values, never the whole file. Searching the raw text
    # let a mention in a comment satisfy the assertion, so a stack could
    # hardcode its tag, leave `# ${IMAGE_FOO:-...}` in a note above it, and
    # pass. Compose interpolation is not YAML, so safe_load hands the
    # `${VAR:-default}` string back untouched and it can be matched directly.
    parsed = yaml.safe_load((STACKS_DIR / stack / "docker-compose.yml").read_text())
    images = "\n".join(
        svc["image"]
        for svc in (parsed.get("services") or {}).values()
        if isinstance(svc, dict) and isinstance(svc.get("image"), str)
    )

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
        # Skip on the (key, owner) pair, never on the key alone. Exempting
        # every `postgres` also exempted the postgres stack's own primary
        # image -- which does read ${IMAGE_POSTGRES:-...} correctly today,
        # so the skip was hiding working code from its own regression test.
        # It would equally have exempted a NEW stack adopting the key, the
        # opposite of what the collision list promises.
        if (key, owner) in KNOWN_SUPPORT_IMAGE_COLLISIONS:
            continue  # collapsed into one IMAGE_* var, tracked in #715
        if (owner, key) in KNOWN_UNREAD_IMAGE_VARS:
            continue
        var = _image_env_var(key)

        # Any valid reference form counts as reading it — ${VAR}, ${VAR:-x},
        # ${VAR:?x}, ${VAR-x}. The question this test asks is whether the
        # compose reads the variable, not which interpolation syntax it uses.
        assert re.search(rf"\$\{{{var}[}}:?-]", images), (
            f"stacks/{stack}/docker-compose.yml does not read ${{{var}}}, which is "
            f"what the deploy emits for the '{key}' image. A version bump in "
            f"services.yaml would silently not reach the container."
        )

        # Separately: the fallback must exist, so the compose still starts
        # standalone when the deploy has not rendered a value.
        assert f"${{{var}:-" in images, (
            f"stacks/{stack}/docker-compose.yml reads ${{{var}}} without a default. "
            f"Use ${{{var}:-<image>}} so the stack starts outside the deploy."
        )


@pytest.mark.parametrize("stack", STACK_DIRS)
def test_every_image_variable_a_compose_reads_is_declared(
    stack: str, services: dict[str, Any]
) -> None:
    """The other direction: a compose must not read a variable nobody emits.

    The test above walks services.yaml and checks each declared key is read.
    That leaves the reverse open, and it is the half that bites more
    quietly: a compose referencing `${IMAGE_SOMETHING}` that the deploy
    never emits always falls back to its hardcoded default, so the version
    in services.yaml cannot reach the container and nothing reports it.

    Five such cases existed before #738 -- planka, woodpecker, ollama and
    openmetadata twice. The comment above KNOWN_UNREAD_IMAGE_VARS used to
    claim a sweep would surface a new one; it would not have, because the
    sweep was run by hand. This makes the claim true.
    """
    emitted = {
        "IMAGE_" + name.replace("-", "_").upper()
        for name, entry in services.items()
        if entry.get("image")
    } | {
        "IMAGE_" + key.replace("-", "_").upper()
        for entry in services.values()
        for key in (entry.get("support_images") or {})
    }

    compose = (STACKS_DIR / stack / "docker-compose.yml").read_text()
    for match in re.finditer(r"\$\{(IMAGE_[A-Z0-9_]+)[}:]", compose):
        var = match.group(1)
        assert var in emitted, (
            f"stacks/{stack}/docker-compose.yml reads ${{{var}}}, which no "
            f"services.yaml entry produces. The compose will always use its "
            f"fallback, so the declared version never reaches the container. "
            f"Add the key, or rename it to match what the deploy emits — the "
            f"variable is `IMAGE_` plus the key, hyphens as underscores, "
            f"uppercased."
        )


@pytest.mark.parametrize("stack", STACK_DIRS)
def test_compose_fallbacks_match_the_declared_version(stack: str, services: dict[str, Any]) -> None:
    """The `:-default` must be the same image services.yaml declares.

    The two checks above ask whether the variable is emitted and whether
    the compose reads it. This asks whether the two agree on the value.

    At deploy time the emitted variable wins, so a mismatch breaks
    nothing — which is exactly why it survives. It shows up when the
    variable is *not* set: a `docker compose up` run by hand on the server
    while investigating one container, or a stack started outside the
    pipeline. `mailpit` fell back to `:latest` while services.yaml pinned
    `v1.28`, so a pin that reads as deliberate held on one code path only.

    `code-server` was the sharper case. Its compose has `build: .` beside
    the `image:` key, so Compose tags the local build with whatever that
    resolves to — and services.yaml named the upstream base image, which
    the container never runs.
    """
    compose = (STACKS_DIR / stack / "docker-compose.yml").read_text()

    declared: dict[str, str] = {}
    for name, entry in services.items():
        if entry.get("image"):
            declared["IMAGE_" + name.replace("-", "_").upper()] = str(entry["image"])
        for key, value in (entry.get("support_images") or {}).items():
            declared["IMAGE_" + key.replace("-", "_").upper()] = str(value)

    for match in re.finditer(r"\$\{(IMAGE_[A-Z0-9_]+):-([^}]*)\}", compose):
        var, fallback = match.group(1), match.group(2)
        if var not in declared:
            continue  # covered by test_every_image_variable_a_compose_reads_is_declared
        assert fallback == declared[var], (
            f"stacks/{stack}/docker-compose.yml falls back to {fallback!r} while "
            f"services.yaml declares {declared[var]!r} for {var}. The deploy "
            f"overrides it, so this only shows when the variable is unset — a "
            f"hand-run `docker compose up` on the server gets the wrong image."
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
    if stack in NAME_CHECK_EXEMPT:
        pytest.skip(f"{stack} is deferred, so compose_runner never name-checks it")

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


@pytest.mark.parametrize("name", sorted(SHARED_DIRECTORY))
def test_directory_sharing_services_are_declared_virtual(name: str) -> None:
    """A service without its own directory must be expanded to a parent.

    seaweedfs-filer and seaweedfs-manager are registered in services.yaml
    but have no `stacks/<name>/` of their own, so they cannot be started
    or looked up under their own name. `compose_runner` handles that by
    mapping them to a parent in `_STACK_PARENTS`: the parent is what gets
    started, and the parent's key is what goes into the `docker ps` check.

    That mapping is the *only* reason those names are exempt from
    `test_a_container_is_named_after_the_service`. Registering another
    directory-sharing service without adding it there gives it neither a
    compose file nor a parent, and the deploy fails on the file check with
    "docker-compose.yml missing for <name>" — before the container-name
    check it would otherwise fail. Asserting against the deploy's own
    table rather than restating it keeps the two from drifting apart.
    """
    assert name in _STACK_PARENTS, (
        f"'{name}' shares another stack's directory but is not in "
        f"compose_runner._STACK_PARENTS, so the deploy would try to start "
        f"stacks/{name}/docker-compose.yml, which does not exist."
    )
    parent = _STACK_PARENTS[name]
    assert parent == SHARED_DIRECTORY[name], (
        f"'{name}' is expanded to parent '{parent}' by the deploy but this "
        f"test file records its directory as '{SHARED_DIRECTORY[name]}'. One "
        f"of the two is wrong."
    )


@pytest.mark.parametrize("name", sorted(_DEFERRED_SERVICES))
def test_deferred_services_never_reach_the_name_check(name: str) -> None:
    """The exemption above rests on this, so assert it rather than trust it.

    `test_a_container_is_named_after_the_service` skips deferred services
    because `expand_targets` drops them before they reach NAMES, so the
    `docker ps --format '{{.Names}}' | grep -qFx` verification never runs
    against their key. Woodpecker is the only one today: it needs Forgejo
    OAuth credentials that exist only after the bootstrap pipeline, so
    `_phase_woodpecker_apply` starts it afterwards with a plain
    `docker compose up -d` and no name check.

    If a service stops being deferred, this test does not fail — it
    disappears, and the exact-name rule starts applying to it instead.
    That is the intended handover. What this guards is the opposite
    direction: a service still listed as deferred that `expand_targets`
    has quietly started returning again, which would exempt it from a
    check it is now subject to.
    """
    parents, leaves = expand_targets([name])
    returned = set(parents) | set(leaves)
    assert name not in returned, (
        f"'{name}' is in _DEFERRED_SERVICES but expand_targets still returns "
        f"it, so compose_runner WILL grep `docker ps` for that exact name. "
        f"Either it is no longer deferred — in which case remove it from "
        f"_DEFERRED_SERVICES — or the skip in "
        f"test_a_container_is_named_after_the_service is now hiding a real "
        f"defect."
    )


@pytest.mark.parametrize("stack", STACK_DIRS)
def test_postgres_containers_keep_their_data_inside_the_volume(stack: str) -> None:
    """A PostgreSQL container must write where its volume is mounted.

    The image default moved in PostgreSQL 18, and the change is easy to
    miss because nothing fails:

        postgres:16-alpine   PGDATA=/var/lib/postgresql/data
                             VOLUME=/var/lib/postgresql/data
        postgres:18-alpine   PGDATA=/var/lib/postgresql/18/docker
                             VOLUME=/var/lib/postgresql

    Bump the tag while mounting at `/var/lib/postgresql/data` and the
    server writes somewhere the volume does not cover. The cluster lands in
    the container's writable layer, the container reports healthy, and
    every `--force-recreate` -- which this project does on each spin-up --
    discards it. An empty database is the only symptom.

    So the check is on the EFFECTIVE path: an explicit PGDATA if the
    service sets one, otherwise the default for that image's major. A
    stack on 16 mounting /var/lib/postgresql/data is correct and stays
    correct; the same mount on 18 is not.

    Relevant to #733: every remaining stage walks into this.
    """
    compose = yaml.safe_load((STACKS_DIR / stack / "docker-compose.yml").read_text())
    for name, svc in (compose.get("services") or {}).items():
        image = str(svc.get("image", ""))
        # TimescaleDB is built on the official postgres image and inherits
        # its PGDATA/VOLUME layout (verified on 2.30.0-pg18), but its name
        # contains no "postgres", so it has to be named here or it would
        # skip the check entirely.
        is_timescale = "timescale/timescaledb" in image
        if not is_timescale and (
            "postgres" not in image or "postgrest" in image or "ducklake" in image
        ):
            continue

        mounts = [
            str(v).rsplit(":", 1)[-1] if ":" in str(v) else str(v)
            for v in (svc.get("volumes") or [])
        ]
        pg_mounts = [m for m in mounts if m.startswith("/var/lib/postgresql")]
        if not pg_mounts:
            continue  # no persistence declared at all; not this check's business

        env = svc.get("environment") or {}
        if isinstance(env, dict):
            pgdata = env.get("PGDATA")
        else:
            pgdata = next(
                (str(e).split("=", 1)[1] for e in env if str(e).startswith("PGDATA=")), None
            )

        if pgdata is None:
            major_match = re.search(r"postgres:(\d+)", image) or re.search(
                r"timescaledb:[^-]+-pg(\d+)", image
            )
            assert major_match, (
                f"{stack}/{name} sets no PGDATA and its image {image!r} carries "
                f"no readable major, so the effective data directory cannot be "
                f"determined. Set PGDATA explicitly."
            )
            major = int(major_match.group(1))
            pgdata = (
                "/var/lib/postgresql/data" if major < 18 else f"/var/lib/postgresql/{major}/docker"
            )

        inside = any(
            str(pgdata) == m or str(pgdata).startswith(m.rstrip("/") + "/") for m in pg_mounts
        )
        assert inside, (
            f"{stack}/{name} writes to {pgdata}, which is outside its mounts "
            f"{pg_mounts}. PostgreSQL 18 moved the image default to "
            f"/var/lib/postgresql/<major>/docker; set PGDATA explicitly to a "
            f"path inside the mount, as stacks/postgres does. Otherwise the "
            f"data lives in the container's writable layer and is discarded "
            f"on the next --force-recreate, with no error."
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


def test_support_image_keys_do_not_shadow_a_service(services: dict[str, Any]) -> None:
    """A support_images key must not be the name of a service.

    Two stacks sharing a support key is one failure mode; this is the
    other, and it is worse, because the two maps are not merged as peers.
    `tofu/stack/outputs.tf` builds image_versions as

        merge(
          { for name, svc in var.services : name => svc.image ... },   # primary
          merge([for name, svc in var.services : svc.support_images]...)  # support
        )

    with support LAST, and Terraform's merge() gives precedence to the
    later argument. So a support key equal to a service name does not
    collide — it *overrides* that service's own image in IMAGE_<NAME>,
    silently, in whichever direction the lexical ordering happens to land.

    A stack could adopt `support_images: {grafana: ...}` today and quietly
    change which image the grafana stack pulls, with nothing failing.
    """
    service_names = set(services)
    shadowing: dict[str, list[str]] = {}
    for name, entry in services.items():
        for key in entry.get("support_images") or {}:
            if key in service_names and key not in KNOWN_PRIMARY_IMAGE_SHADOWING:
                shadowing.setdefault(key, []).append(name)

    assert not shadowing, (
        f"support_images keys that shadow a service's own image: {shadowing}. "
        f"support_images is merged after the primary images, so IMAGE_<KEY> "
        f"would carry the support value and the service's own image would "
        f"never reach its container. Prefix the key with the stack name, as "
        f"dify-postgres and forgejo-postgres do."
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


def test_core_services_are_the_documented_five(services: dict[str, Any]) -> None:
    """`core: true` means always deployed and not disableable.

    Pinned because the set is small, load-bearing, and has changed silently
    before — Gitea held a place here until the Forgejo migration took it.

    SFTPGo joined so that every deployment can see what is in its object
    storage. It is not the only browser — filestash covers R2 and Hetzner,
    s3manager covers Hetzner — but all three were optional, so a default
    deployment had none. SFTPGo takes the slot because it also speaks SFTP.
    """
    core = {name for name, entry in services.items() if entry.get("core")}
    assert core == {"forgejo", "grafana", "infisical", "portainer", "sftpgo"}, (
        f"core services changed to {sorted(core)}. That is a deliberate decision; "
        f"update this test and the docs together."
    )


# Hosts a shipped Evidence source may name without being defined in
# stacks/evidence/docker-compose.yml. Empty on purpose: everything this
# repo ships points at the stack's own database. An entry here is a
# promise that the host is reachable from every deployment, which is a
# claim no in-stack hostname needs and no other stack's container can
# make -- so adding one wants a reason next to it.
EVIDENCE_EXTERNAL_SOURCE_HOSTS: set[str] = set()


def test_evidence_sources_only_name_hosts_its_own_compose_defines(
    services: dict[str, Any],
) -> None:
    """Evidence's shipped data sources must resolve inside the stack.

    The stack originally pointed its bundled source at the shared
    `postgres` stack, which is not core and so is off unless the operator
    enables it. Evidence's entrypoint runs `npm run sources` before the
    dev server and treats an unreachable source as fatal, so a stack that
    enabled Evidence alone crash-looped on `getaddrinfo EAI_AGAIN
    postgres` with ExitCode=1 rather than serving a page with one broken
    query.

    The check is "host is defined by Evidence's own compose", not "host
    is some other stack's service". The narrower form let a typo through
    -- `evidenc-db` is in no services.yaml, so it would have passed while
    failing at runtime exactly like the defect this guards.

    Scope note, so this docstring does not overclaim: there is no
    repo-wide check that a stack never depends on a non-core stack's
    container name, and this test does not add one. It pins the one place
    the defect actually shipped -- the connection files this repo ships
    for Evidence. A user-added source under the same directory on a live
    server is outside what the repo can see, which is why pages/index.md
    warns about the same failure mode in prose.
    """
    stack_dir = STACKS_DIR / "evidence"
    compose = yaml.safe_load((stack_dir / "docker-compose.yml").read_text())
    own_services = set(compose.get("services", {}))

    connections = sorted((stack_dir / "project" / "sources").glob("*/connection.yaml"))
    assert connections, "Evidence ships no data source; this test would pass vacuously"

    offenders = {}
    for path in connections:
        host = (yaml.safe_load(path.read_text()).get("options") or {}).get("host")
        if host not in own_services and host not in EVIDENCE_EXTERNAL_SOURCE_HOSTS:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = host

    assert not offenders, (
        f"Evidence source names a host its own compose does not define: {offenders}. "
        f"An unreachable source stops Evidence from starting at all, so this covers "
        f"three cases at once: another stack's container (not guaranteed to be "
        f"running), a typo, and an external host nobody vetted. Define the host in "
        f"stacks/evidence/docker-compose.yml, or -- if it really is external and "
        f"always reachable -- add it to EVIDENCE_EXTERNAL_SOURCE_HOSTS with a reason."
    )


def test_strict_host_check_only_where_a_tunnel_rule_exists(services: dict[str, Any]) -> None:
    """`strict_host_check` rewrites the Host header on a tunnel ingress
    rule, so it needs a rule to act on.

    An `internal_only` service has no subdomain and therefore gets no
    ingress rule (main.tf iterates `enabled_services_with_subdomain`), so
    the flag would sit in services.yaml doing nothing -- the failure mode
    where someone sets it, sees no change, and looks for the cause
    elsewhere.

    .github/scripts/generate-services-tfvars.py rejects the same
    combination, but only when a deploy runs it. This catches it on the
    commit instead.
    """
    offenders = sorted(
        name
        for name, entry in services.items()
        if entry.get("strict_host_check")
        and (entry.get("internal_only") or not entry.get("subdomain"))
    )
    assert not offenders, (
        f"strict_host_check set on services with no tunnel ingress rule: {offenders}. "
        f"The flag only has an effect on a service with a subdomain."
    )


# Values a credential-shaped variable must never fall back to. `admin`,
# `root` and `postgres` are the names CLAUDE.md's "Service Account Naming
# Convention" forbids outright; a stack's own name is the "service name
# alone" half of the same rule.
_FORBIDDEN_CREDENTIAL_DEFAULTS = frozenset({"admin", "root", "postgres", "administrator"})

# A variable whose value is a credential rather than configuration.
# Matched on the name, because that is all a compose file exposes.
#
# The name grammar is Compose's own -- `[_a-zA-Z][_a-zA-Z0-9]*`, matched
# case-insensitively -- not the SHOUTING_CASE this repo happens to use.
# An upper-case-only pattern would skip `${grafana_admin_user:-admin}`,
# which Compose accepts and which is the same defect in different
# clothes. The only lower-case interpolations in the tree today are
# `${domain}`, `${subdomain}` and `${var.domain}`; none is credential-
# shaped and none carries a default, so widening costs no false hits.
_CREDENTIAL_VAR = re.compile(
    r"\$\{(?P<var>[_a-zA-Z][_a-zA-Z0-9]*?"
    r"(?:USER|USERNAME|PASS|PASSWORD|SECRET|TOKEN|KEY|ADMIN|ROOT)"
    r"[_a-zA-Z0-9]*):-(?P<default>[^}]*)\}",
    re.IGNORECASE,
)

# `${IMAGE_FOO:-org/foo:1.2}` is the house pattern that lets the
# orchestrator override a pinned tag, and ~140 of them exist. The
# exemption is the `image:` line rather than the `IMAGE_` prefix, because
# a name-based one would wave through a genuine credential that happened
# to be called `IMAGE_REGISTRY_PASSWORD`. Every IMAGE_ fallback in the
# tree sits on an image: line today, so this exempts exactly the same set
# while keying on what the value *is*. Two of them -- IMAGE_ADMINER and
# IMAGE_PGADMIN -- match the credential name pattern above, which is
# precisely why the exemption cannot be the name.
_IMAGE_FIELD = re.compile(r"^\s*image:\s")


def test_no_credential_variable_falls_back_to_a_guessable_default() -> None:
    """A credential env var must not carry a guessable default.

    `${ADMIN_USERNAME:-admin}` hands back exactly the name the `nexus-`
    prefix rule exists to prevent, and `:-` fires on an *empty* value too,
    not only on an unset one -- so it is reachable whenever an upstream
    step produces a blank rather than failing.

    Four of these existed when this test was written (#780): grafana,
    mage, litellm and rustfs. The fix is `${VAR:?<where it comes from>}`,
    the pattern infisical/hoppscotch/questdb already use, so a stack whose
    credential is missing refuses to start instead of starting wrong.

    An empty default (`${VAR:-}`) is allowed: it hands back nothing, which
    is not guessable and generally fails downstream on its own.
    """
    offenders: list[str] = []
    for stack in STACK_DIRS:
        text = (STACKS_DIR / stack / "docker-compose.yml").read_text()
        for line in text.splitlines():
            if _IMAGE_FIELD.match(line):
                continue
            for match in _CREDENTIAL_VAR.finditer(line):
                default = match.group("default").strip()
                if not default:
                    continue
                if default.lower() in _FORBIDDEN_CREDENTIAL_DEFAULTS or default.lower() == stack:
                    offenders.append(f"{stack}: ${{{match.group('var')}:-{default}}}")

    assert not offenders, (
        "credential variables fall back to a guessable default:\n  "
        + "\n  ".join(sorted(offenders))
        + "\nUse ${VAR:?must be set in .env (rendered by service_env._render_<stack>)} "
        "instead, so the stack fails loudly rather than starting with a name "
        "an attacker would try first. See CLAUDE.md, 'Service Account Naming "
        "Convention', and #780."
    )


def test_no_compose_configures_spark_through_spark_hadoop_env_vars() -> None:
    """`SPARK_HADOOP_*` configures nothing in the official Spark image.

    The Bitnami Spark image translates `SPARK_HADOOP_foo_bar` into
    `spark.hadoop.foo.bar`. The official `apache/spark` image does not, and
    Spark itself reads only AWS_ENDPOINT_URL / AWS_ACCESS_KEY_ID /
    AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN from the environment:

        $ docker run --rm --entrypoint sh apache/spark:4.2.0 \\
            -c 'grep -c SPARK_HADOOP /opt/entrypoint.sh'
        0

    This stack carried such a block on all three Spark containers for
    months. It was inert the whole time; S3 access worked from Jupyter only
    because `stacks/jupyter/spark-init.py` reads the same variables with
    `os.environ.get()` and applies them by hand. The replacement is a
    rendered `spark-defaults.conf`, which Spark does read.

    The variables look exactly like configuration, which is why this guards
    against them coming back rather than trusting anyone to remember.

    Jupyter is the exception and the rule accounts for it rather than
    listing it: `stacks/jupyter/spark-init.py` reads the same names with
    `os.environ.get()` and calls `.config(...)` by hand, so there they are
    consumed. The check therefore asks whether anything in the same stack
    directory reads the variable — an allowlist would have to be kept in
    step with the code, and would not be.
    """
    offenders: list[str] = []
    for name in STACK_DIRS:
        path = STACKS_DIR / name
        compose = path / "docker-compose.yml"
        setters = [
            (number, line.strip(), match.group(0))
            for number, line in enumerate(compose.read_text().splitlines(), 1)
            if not line.lstrip().startswith("#")
            for match in [re.search(r"SPARK_HADOOP_[A-Za-z0-9_]+", line)]
            if match
        ]
        if not setters:
            continue

        # Per variable name, not per prefix. A stack that sets four
        # SPARK_HADOOP_* variables and reads one of them would otherwise
        # have all four excused by the single reader.
        #
        # Comment lines do not count as readers: this file's own
        # explanation names the variables, and so does
        # stacks/spark/spark-defaults.conf.template, which documents why
        # they were removed. Counting prose as a reader made the first
        # version of this check pass a re-added block — confirmed by
        # mutation, not by reasoning.
        readers: set[str] = set()
        for sibling in path.iterdir():
            if not sibling.is_file() or sibling.name == "docker-compose.yml":
                continue
            for line in sibling.read_text(errors="ignore").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                readers.update(re.findall(r"SPARK_HADOOP_[A-Za-z0-9_]+", line))

        offenders += [
            f"{compose}:{number}: {text}" for number, text, name in setters if name not in readers
        ]

    assert not offenders, (
        "compose files setting SPARK_HADOOP_* variables that nothing reads:\n  "
        + "\n  ".join(offenders)
        + "\nThe official apache/spark image ignores these. Put the setting in "
        "the rendered spark-defaults.conf instead (service_env._render_spark)."
    )


def test_unity_catalog_writes_under_its_own_prefix() -> None:
    """Unity Catalog owns a subtree of the data bucket, not its root.

    The bucket is shared. Lakekeeper scopes itself with `key-prefix: lakekeeper`
    and pg-ducklake writes its own tables there, but Unity Catalog used to
    append nothing, so a table created as `unity.demo.cities` landed at
    `s3://<bucket>/demo/cities` — a top-level folder named after a schema,
    saying nothing about which stack made it and colliding outright with any
    other stack that picked the same word.

    Asserted on the rendered property rather than on the prefix constant alone:
    the constant existing proves nothing if the bucketPath line stops using it.
    """
    entrypoint = (REPO_ROOT / "stacks/unity-catalog/entrypoint.sh").read_text()

    prefix_lines = [line for line in entrypoint.splitlines() if line.startswith("UC_R2_PREFIX=")]
    assert prefix_lines == ['UC_R2_PREFIX="unity-catalog"'], prefix_lines

    bucket_paths = [line for line in entrypoint.splitlines() if line.startswith("s3.bucketPath.")]
    assert bucket_paths == ["s3.bucketPath.0=s3://${UC_R2_BUCKET}/${UC_R2_PREFIX}"], (
        f"bucketPath no longer carries the prefix: {bucket_paths}. Writing to the "
        "bucket root puts Unity Catalog's schemas next to every other stack's data."
    )


def test_lakekeeper_advertises_its_in_cluster_address() -> None:
    """`LAKEKEEPER__BASE_URI` must be the in-cluster URL, not the public one.

    Lakekeeper echoes BASE_URI to Iceberg clients as `overrides.uri` in its
    `/v1/config` response, and PyIceberg honours it for every subsequent call.
    Pointed at the Cloudflare-Access-gated hostname, the client fetches config
    successfully over app-network, switches to the public URL, receives an
    HTML login page and dies parsing it as JSON -- with `load_catalog()`
    having succeeded, so the failure surfaces one call later than its cause.

    Measured both ways against v0.13.3:
        BASE_URI=https://lakekeeper.example.com -> overrides.uri = https://...
        BASE_URI=http://lakekeeper:8181         -> overrides.uri = http://lakekeeper:8181/catalog

    The UI keeps the public address through its own setting, which upstream
    documents as defaulting to BASE_URI -- so narrowing one without setting
    the other would point the browser inward instead.
    """
    compose = (REPO_ROOT / "stacks/lakekeeper/docker-compose.yml").read_text()

    base = [
        line.split(":", 1)[1].strip()
        for line in compose.splitlines()
        if line.strip().startswith("LAKEKEEPER__BASE_URI:")
    ]
    assert base == ["http://lakekeeper:8181"], (
        f"LAKEKEEPER__BASE_URI is {base}. Anything public here is handed to "
        "Iceberg clients as overrides.uri and routes them into Cloudflare Access."
    )

    ui = [
        line.split(":", 1)[1].strip()
        for line in compose.splitlines()
        if line.strip().startswith("LAKEKEEPER__UI__LAKEKEEPER_URL:")
    ]
    assert ui == ["https://${LAKEKEEPER_DOMAIN}"], (
        f"LAKEKEEPER__UI__LAKEKEEPER_URL is {ui}. Without it the browser UI "
        "inherits the in-cluster BASE_URI, which no browser can reach."
    )


def test_marimo_disables_botocore_streaming_checksums() -> None:
    """Writes through a remote-signing Iceberg warehouse need this on R2.

    Lakekeeper signs the request it is shown; botocore then re-encodes the
    body as `aws-chunked` with trailing checksums, so the body the signature
    covers is not the body that arrives. R2 answers with
    `The request signature we calculated does not match the signature you
    provided`, or `MissingContentLength`.

    Measured against the live warehouse, same table and code, only these two
    variables added: without them the write fails, with them it returns rows.

    Pinned because the failure is silent in the worst way -- it only appears
    once remote signing itself works, so an unrelated signing bug masks it
    completely, and removing these would look harmless in any environment
    that is already broken further upstream.

    Parsed from the YAML rather than grepped. The first version of this test
    matched the raw text, and a mutation proved it worthless: commenting the
    line out left the test passing. A check that accepts a disabled setting
    is worse than no check, because it reports the opposite of the truth.
    """
    import yaml

    compose = yaml.safe_load((REPO_ROOT / "stacks/marimo/docker-compose.yml").read_text())
    raw = compose["services"]["marimo"]["environment"]
    # compose accepts either a list of "KEY=value" or a mapping
    env = dict(item.split("=", 1) for item in raw) if isinstance(raw, list) else dict(raw)

    for var in ("AWS_REQUEST_CHECKSUM_CALCULATION", "AWS_RESPONSE_CHECKSUM_VALIDATION"):
        assert env.get(var) == "when_required", (
            f"{var} is {env.get(var)!r}, expected 'when_required'. Iceberg "
            "writes to R2 fail with a signature mismatch without it."
        )


def _mlflow_service() -> dict[str, object]:
    """The `mlflow` service block, parsed from its compose file.

    Parsed rather than grepped, for the reason spelled out on the Marimo
    checksum test above: a substring scan happily matches a commented-out
    line, and a check that accepts a disabled setting reports the opposite
    of the truth.
    """
    import yaml

    compose = yaml.safe_load((REPO_ROOT / "stacks/mlflow/docker-compose.yml").read_text())
    return dict(compose["services"]["mlflow"])


def _mlflow_command_value(flag: str) -> str:
    """The argument following `flag` in the mlflow server command."""
    command = _mlflow_service()["command"]
    assert isinstance(command, list), "mlflow command must stay a list, not a shell string"
    assert flag in command, f"{flag} missing from the mlflow server command: {command}"
    return str(command[command.index(flag) + 1])


def _neo4j_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "neo4j" / "docker-compose.yml").read_text()))


def test_neo4j_container_gets_no_unknown_neo4j_variable() -> None:
    """The image turns every NEO4J_* variable into a neo4j.conf setting.

    An unknown one stops the server before it starts -- measured with
    NEO4J_PASSWORD: "Unrecognized setting. No declared setting with name:
    PASSWORD". Two ways to walk into that: an `env_file` (which hands the
    container every key in .env), or a NEO4J_* key that is not a setting. So
    no env_file at all, and only the NEO4J_* keys the stack deliberately sets.
    """
    neo4j = _neo4j_compose()["services"]["neo4j"]
    assert "env_file" not in neo4j, (
        "stacks/neo4j must not use env_file: the image reads every NEO4J_* "
        "variable as a setting and refuses to start on an unknown one"
    )
    allowed = {
        "NEO4J_AUTH",
        "NEO4J_server_memory_heap_initial__size",
        "NEO4J_server_memory_heap_max__size",
        "NEO4J_server_memory_pagecache_size",
        "NEO4J_dbms_usage__report_enabled",
    }
    unexpected = {k for k in neo4j["environment"] if k.startswith("NEO4J_")} - allowed
    assert not unexpected, (
        f"unexpected NEO4J_* variables {sorted(unexpected)}: each becomes a "
        "neo4j.conf setting. Verify the setting exists in the pinned version, "
        "then add it here."
    )


def test_neo4j_tunnel_origin_is_the_proxy_that_routes_bolt() -> None:
    """Neo4j Browser runs queries over a Bolt WebSocket, not over the HTTP port.

    The tunnel maps neo4j.<domain> to one local port. That port has to be
    neo4j-proxy, which sends WebSocket upgrades to Bolt (7687) and the rest to
    HTTP (7474). Pointing services.yaml's port at Neo4j's own HTTP port
    instead would give a Browser page that loads and never connects.
    """
    compose = _neo4j_compose()
    port = SERVICES["neo4j"]["port"]
    proxy_ports = compose["services"]["neo4j-proxy"]["ports"]
    assert any(str(p).startswith(f"127.0.0.1:{port}:") for p in proxy_ports), (
        f"services.yaml sends the tunnel to localhost:{port}, but neo4j-proxy "
        f"publishes {proxy_ports}"
    )
    neo4j_ports = compose["services"]["neo4j"].get("ports", [])
    assert not any(f":{port}:" in str(p) for p in neo4j_ports), (
        "neo4j must not publish the tunnel port itself; the proxy owns it"
    )

    conf = (STACKS_DIR / "neo4j" / "nginx.conf").read_text()
    assert re.search(r'"~\*\^websocket\$"\s+"neo4j:7687";', conf), (
        "nginx.conf must route WebSocket upgrades to neo4j:7687"
    )
    assert re.search(r'default\s+"neo4j:7474";', conf), (
        "nginx.conf must route ordinary requests to neo4j:7474"
    )


def test_neo4j_proxy_points_browser_discovery_at_443() -> None:
    """Neo4j Browser connects to the Bolt URL its discovery document names.

    Neo4j writes ``neo4j://<host>:7687`` there, and the tunnel serves nothing
    on 7687: the first spin-up of this stack loaded the Browser fine and then
    hung on every login. The proxy rewrites both Bolt URLs to
    ``bolt+s://<host>:443``, which it does serve.

    Checked in the ``location = /`` block specifically, because that is the
    only path discovery is fetched from; a rewrite in the catch-all block
    would also work today, but would scan every response the Browser loads.
    """
    conf = (STACKS_DIR / "neo4j" / "nginx.conf").read_text()
    block = re.search(r"location = / \{(.*?)\n        \}", conf, re.S)
    assert block, "nginx.conf needs a `location = /` block for discovery"
    body = "\n".join(line.split("#", 1)[0] for line in block.group(1).splitlines())

    assert "proxy_pass http://$neo4j_upstream;" in body, (
        "`location = /` must keep the Upgrade-based upstream: the Browser opens "
        "its WebSocket on `/` too, and that has to reach Bolt"
    )
    assert re.search(r"sub_filter_types\s+application/json;", body), (
        "only the JSON discovery document may be rewritten"
    )
    assert re.search(r"sub_filter_once\s+off;", body), (
        "discovery names Bolt twice (bolt_routing, bolt_direct); both need rewriting"
    )
    assert re.search(r'proxy_set_header\s+Accept-Encoding\s+"";', body), (
        "sub_filter cannot rewrite a compressed body"
    )
    for scheme in ("neo4j", "bolt"):
        assert re.search(
            rf'sub_filter\s+"{scheme}://\$host:7687"\s+"bolt\+s://\$host:443";', body
        ), f"discovery's `{scheme}://<host>:7687` must become `bolt+s://<host>:443`"


def test_mlflow_command_names_the_executable() -> None:
    """The image declares no ENTRYPOINT, so the command must start with one.

    `ghcr.io/mlflow/mlflow:v3.16.0` has `ENTRYPOINT: null` and
    `CMD: ["python3"]`. A command list beginning with `server` therefore asks
    Docker to execute a binary of that name, and the container never starts:
    `compose up failed (rc=1)`, the container left in STATE:created, and
    nothing in `docker logs` because it had not begun running.

    This shipped. Every local rehearsal passed `--entrypoint mlflow` on the
    `docker run` line, which supplied exactly the piece the compose file was
    missing -- so the tested configuration and the shipped one differed by the
    one thing that mattered, and every test passed.

    Hence a guard on the compose file itself rather than on a container that
    was started some other way.
    """
    command = _mlflow_service()["command"]
    assert isinstance(command, list), "mlflow command must stay a list, not a shell string"
    assert command, "mlflow command must not be empty"
    assert command[0] == "mlflow", (
        f"the mlflow command starts with {command[0]!r}; the image has no "
        "ENTRYPOINT, so the first element must be the executable"
    )
    assert command[1] == "server", f"expected `mlflow server`, got `mlflow {command[1]}`"


def test_mlflow_writes_artifacts_under_its_own_prefix() -> None:
    """The R2 data bucket is shared; MLflow may not address its root.

    Lakekeeper owns `lakekeeper/` and Unity Catalog owns `unity-catalog/`.
    A `--artifacts-destination` pointing at the bucket root would scatter run
    artifacts among their table data, where nothing identifies which stack
    wrote what -- and a later prefix-wide cleanup would take the wrong files.
    """
    destination = _mlflow_command_value("--artifacts-destination")
    assert destination.endswith("/mlflow"), (
        f"--artifacts-destination is {destination!r}; it must end in '/mlflow' "
        "so artifacts stay inside this stack's own prefix"
    )


def test_mlflow_allows_both_hostnames_it_must_answer_to() -> None:
    """MLflow 3.x rejects an unexpected Host header outright.

    The response is `403 Invalid Host header - possible DNS rebinding attack
    detected`, with no hint about what to change. Two names must be listed and
    each covers a different caller:

    - `mlflow:5000` -- Marimo and Jupyter on app-network
    - `${MLFLOW_DOMAIN}` -- the browser, through the tunnel

    Dropping either leaves a server that is healthy, answers /health, and
    refuses half its clients. Measured: with this flag set, `mlflow:5000`
    returns 200, an unlisted host returns 403 -- and so does
    `localhost:5000`, because setting the flag REPLACES the built-in default
    rather than extending it.
    """
    allowed = _mlflow_command_value("--allowed-hosts")
    hosts = {h.strip() for h in allowed.split(",")}
    assert "mlflow:5000" in hosts, (
        f"--allowed-hosts is {allowed!r}; without 'mlflow:5000' every notebook "
        "on app-network gets a 403"
    )
    assert "${MLFLOW_DOMAIN}" in hosts, (
        f"--allowed-hosts is {allowed!r}; without '${{MLFLOW_DOMAIN}}' the "
        "browser gets a 403 through the tunnel"
    )


def test_mlflow_disables_botocore_streaming_checksums() -> None:
    """R2 has answered `MissingContentLength` to `aws-chunked` bodies.

    Note this is NOT the failure that bit PyIceberg, and the distinction
    matters so nobody removes these as cargo cult: there the cause was remote
    signing specifically -- Lakekeeper signed, botocore then re-encoded the
    body, and the signature covered something else. MLflow holds the
    credentials and signs the final body itself.

    They stay because the `aws-chunked` encoding has caused trouble against R2
    independently of signing, and `when_required` restores the pre-1.36
    botocore behaviour at no cost.
    """
    environment = _mlflow_service()["environment"]
    assert isinstance(environment, dict), "mlflow environment must stay a mapping"
    env = dict(environment)
    for var in ("AWS_REQUEST_CHECKSUM_CALCULATION", "AWS_RESPONSE_CHECKSUM_VALIDATION"):
        assert env.get(var) == "when_required", (
            f"{var} is {env.get(var)!r}, expected 'when_required'."
        )


def test_mlflow_clients_install_the_skinny_package() -> None:
    """Notebook images get the tracking client, not the whole server.

    Measured on the Marimo base image: `mlflow-skinny` costs 78 MB,
    `mlflow` costs 465 MB, because the full package declares `scikit-learn<2`
    and `scipy<2` as hard dependencies and pulls matplotlib with them. None of
    that is needed to log a run.

    Asserted on both notebook stacks because they install it by different
    mechanisms -- Marimo has a Dockerfile, Jupyter installs at container start
    -- so a change to one does not surface in the other.
    """
    # Quote-independent: `mlflow==3.16.0`, `"mlflow==3.16.0"` and
    # `'mlflow==3.16.0'` are the same install and must all be caught. An
    # earlier version of this check keyed on the double quote alone, which a
    # reviewer pointed out would wave through two of the three spellings.
    # `\b` before the name keeps `mlflow-skinny==` from matching, since a
    # hyphen is a word boundary — hence the explicit negative lookahead too.
    full_mlflow = re.compile(r"\bmlflow(?!-skinny)\s*==")

    for label, path in (
        ("Marimo", "stacks/marimo/Dockerfile"),
        ("Jupyter", "stacks/jupyter/docker-compose.yml"),
    ):
        # Whole comment lines dropped before scanning. Both files explain in
        # prose why skinny was chosen, and that prose names `mlflow==3.16.0`
        # as the thing not to install -- so a raw scan trips on its own
        # documentation. Caught on the first run, which is the third time a
        # guard in this file has done that; only full-line comments are
        # removed, so nothing inside the Jupyter command block is touched.
        source = "\n".join(
            line
            for line in (REPO_ROOT / path).read_text().splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "mlflow-skinny==" in source, f"{label} must install mlflow-skinny"
        assert not full_mlflow.search(source), (
            f"{label} installs full mlflow; that is +465 MB against skinny's "
            "+78 MB, because full MLflow declares scikit-learn and scipy as "
            "hard dependencies. If a seed genuinely needs scikit-learn, add "
            "that package explicitly instead."
        )


def test_notebook_stacks_point_at_the_in_cluster_mlflow() -> None:
    """The public hostname fails twice over, and neither failure names a URL.

    Cloudflare Access answers an API client with an HTML login page, and
    MLflow's own Host-header check refuses the name besides. Both notebook
    stacks therefore carry the in-cluster address -- container port 5000, not
    the host-published 5001.
    """
    import yaml

    for stack, service in (("marimo", "marimo"), ("jupyter", "jupyter")):
        compose = yaml.safe_load((REPO_ROOT / f"stacks/{stack}/docker-compose.yml").read_text())
        raw = compose["services"][service]["environment"]
        env = dict(item.split("=", 1) for item in raw) if isinstance(raw, list) else dict(raw)
        assert env.get("MLFLOW_TRACKING_URI") == "http://mlflow:5000", (
            f"{stack} has MLFLOW_TRACKING_URI={env.get('MLFLOW_TRACKING_URI')!r}; "
            "it must be the in-cluster address http://mlflow:5000"
        )


def _temporal_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "temporal" / "docker-compose.yml").read_text()))


def test_temporal_publishes_every_port_on_loopback_only() -> None:
    """Neither Temporal port authenticates, so neither may bind every interface.

    The gRPC frontend on 7233 accepts any client that can reach it and lets
    that client start, signal or terminate any workflow; the Web UI has no
    login. `tcp_ports` is already kept away from this stack by
    NO_OWN_AUTH, but that only governs the Hetzner firewall rule. A bare
    `"7233:7233"` in the compose file would still listen on the public
    interface, leaving the firewall as the single control -- #742 is the
    backlog of stacks in exactly that state, and this one should not join it.

    Loopback costs nothing: cloudflared reaches the UI over localhost, and
    the documented laptop-worker path is `ssh -N -L 7233:localhost:7233`.
    """
    offenders = [
        f"{name}: {port}"
        for name, svc in (_temporal_compose().get("services") or {}).items()
        for port in (svc.get("ports") or [])
        if not str(port).startswith("127.0.0.1:")
    ]
    assert not offenders, (
        f"stacks/temporal publishes ports on every interface: {offenders}. "
        "Prefix each with 127.0.0.1: -- neither the frontend nor the UI "
        "has authentication of its own."
    )


def test_temporal_ui_waits_for_the_namespace_job() -> None:
    """`docker compose up -d` only waits for what something depends on.

    Nothing else depends on `temporal-create-namespace`, so without this edge
    the job runs detached: `up` returns 0, the deploy's `docker ps` check
    finds `temporal` running and reports success, and a failed namespace
    creation surfaces only as `Namespace default is not found` in the first
    SDK call. The mechanism was measured on the sibling edge from `temporal`
    to `temporal-schema-setup`: run against a wrong database password, the
    one-shot exits 1 and `docker compose up -d` exits 1 with
    `service "temporal-schema-setup" didn't complete successfully: exit 1`.
    """
    ui = _temporal_compose()["services"]["temporal-ui"]
    condition = (ui.get("depends_on") or {}).get("temporal-create-namespace", {}).get("condition")
    assert condition == "service_completed_successfully", (
        "temporal-ui must depend on temporal-create-namespace with "
        f"condition service_completed_successfully, got {condition!r}"
    )


def _langfuse_services() -> dict[str, dict[str, Any]]:
    """The Langfuse compose file's services, parsed.

    Parsed rather than grepped for the reason given on the Marimo checksum
    test: a substring scan matches a commented-out line. PyYAML's safe_load
    resolves the `<<: *langfuse-env` merge key, so the shared block is seen
    in each service exactly as Compose sees it.
    """
    compose = yaml.safe_load((REPO_ROOT / "stacks/langfuse/docker-compose.yml").read_text())
    return {name: dict(svc) for name, svc in compose["services"].items()}


def _langfuse_env(service: str) -> dict[str, str]:
    raw = _langfuse_services()[service].get("environment") or {}
    assert isinstance(raw, dict), f"langfuse/{service} environment must stay a mapping"
    return {str(k): str(v) for k, v in raw.items()}


@pytest.mark.parametrize("service", ["langfuse", "langfuse-worker"])
def test_langfuse_runs_clickhouse_migrations_without_on_cluster(service: str) -> None:
    """Langfuse's env schema defaults CLICKHOUSE_CLUSTER_ENABLED to `true`.

    That runs every ClickHouse migration `ON CLUSTER`, which a single node
    does not have. Upstream's configuration reference says to set it to
    `false` for single-container setups -- this stack is one.
    """
    assert _langfuse_env(service).get("CLICKHOUSE_CLUSTER_ENABLED") == "false"


@pytest.mark.parametrize("service", ["langfuse", "langfuse-worker"])
def test_langfuse_binds_to_all_interfaces(service: str) -> None:
    """Both containers bind to $HOSTNAME, which Docker sets to the container id.

    Measured on the worker without the override: it logged
    `Listening: http://<container-id>:3030` and the healthcheck against
    127.0.0.1 was refused, while the worker itself ran fine -- a container
    that would sit `unhealthy` forever and hold back nothing but its status.
    """
    assert _langfuse_env(service).get("HOSTNAME") == "0.0.0.0"  # noqa: S104 - asserting config, not binding


@pytest.mark.parametrize("service", ["langfuse", "langfuse-worker"])
def test_langfuse_writes_blobs_under_its_own_prefix(service: str) -> None:
    """The R2 data bucket is shared; Langfuse may not address its root.

    Lakekeeper owns `lakekeeper/`, Unity Catalog `unity-catalog/`, MLflow
    `mlflow/`. An empty prefix is upstream's default and would scatter event
    files among their data. Upstream also requires a prefix to end in `/`.
    """
    env = _langfuse_env(service)
    for var in ("LANGFUSE_S3_EVENT_UPLOAD_PREFIX", "LANGFUSE_S3_MEDIA_UPLOAD_PREFIX"):
        prefix = env.get(var, "")
        assert prefix.startswith("langfuse/"), (
            f"langfuse/{service} has {var}={prefix!r}; it must start with 'langfuse/'"
        )
        assert prefix.endswith("/"), (
            f"langfuse/{service} has {var}={prefix!r}; upstream requires a trailing '/'"
        )


def test_langfuse_disables_sign_up_and_telemetry() -> None:
    """Sign-up off: the only account is the headlessly initialised admin, who
    invites anyone else. Telemetry off: upstream's default sends usage data."""
    env = _langfuse_env("langfuse")
    assert env.get("AUTH_DISABLE_SIGNUP") == "true"
    assert env.get("TELEMETRY_ENABLED") == "false"


def test_langfuse_initialises_an_admin_it_can_log_in_with() -> None:
    """With sign-up disabled, a missing init user is a Langfuse nobody can
    enter. The initialiser needs BOTH email and password, and does nothing
    at all without an org id -- it only logs a warning."""
    env = _langfuse_env("langfuse")
    for var in (
        "LANGFUSE_INIT_ORG_ID",
        "LANGFUSE_INIT_PROJECT_ID",
        "LANGFUSE_INIT_USER_EMAIL",
        "LANGFUSE_INIT_USER_PASSWORD",
        "LANGFUSE_INIT_PROJECT_PUBLIC_KEY",
        "LANGFUSE_INIT_PROJECT_SECRET_KEY",
    ):
        assert env.get(var), f"langfuse is missing {var}"


def _to_bytes(size: str) -> int:
    units = {"k": 1024, "m": 1024**2, "g": 1024**3}
    size = size.strip().lower().rstrip("b")
    return int(float(size[:-1]) * units[size[-1]]) if size[-1] in units else int(size)


def test_every_langfuse_container_has_a_memory_limit() -> None:
    """Six containers on a 16 GB host shared by dozens of stacks.

    Each is bounded, and the web container is bounded at no less than 2g.
    Node sizes its heap from the cgroup limit: on Langfuse 3.225.7 at 1536m
    the web container died on startup with `JavaScript heap out of memory`
    three times in a row, its healthcheck passing between the crashes. On
    4.36.0 the same limit started cleanly but idled at ~815 MiB resident,
    too close to that ceiling to drop the headroom.
    """
    services = _langfuse_services()
    for name, svc in services.items():
        limit = ((svc.get("deploy") or {}).get("resources") or {}).get("limits", {}).get("memory")
        assert limit, f"langfuse/{name} has no deploy.resources.limits.memory"
    web_limit = services["langfuse"]["deploy"]["resources"]["limits"]["memory"]
    assert _to_bytes(str(web_limit)) >= 2 * 1024**3, (
        f"langfuse web memory limit is {web_limit}; below 2g it crash-loops on heap OOM"
    )


def test_langfuse_redis_never_evicts() -> None:
    """Langfuse's ingestion queues live in this Redis. An evicted key is a job
    that silently never runs, so the policy must be `noeviction`."""
    command = _langfuse_services()["langfuse-redis"]["command"]
    assert isinstance(command, list), "langfuse-redis command must stay a list"
    assert "--maxmemory-policy" in command
    assert command[command.index("--maxmemory-policy") + 1] == "noeviction"


def _keycloak_service() -> dict[str, Any]:
    compose = yaml.safe_load((STACKS_DIR / "keycloak" / "docker-compose.yml").read_text())
    return dict(compose["services"]["keycloak"])


def test_keycloak_runs_in_production_mode() -> None:
    """`start`, never `start-dev`.

    The image's entrypoint is kc.sh, so the command list is kc.sh's arguments.
    `start-dev` would switch to the development profile, whose defaults
    `kc.sh start --help-all` describes as different from production's (HTTP
    and a local cache enabled by default). Upstream does not support it for
    production use, and a container started that way still turns healthy, so
    nothing downstream would notice.
    """
    command = _keycloak_service()["command"]
    assert isinstance(command, list), "keycloak command must stay a list"
    assert command, "keycloak command must not be empty"
    assert command[0] == "start", (
        f"keycloak command is {command!r}; it must begin with `start` "
        "(production mode), not `start-dev`"
    )


def test_keycloak_does_not_publish_the_management_port() -> None:
    """Only the HTTP listener reaches the host; 9000 stays inside Docker.

    The management interface serves /health (and /metrics, if ever enabled).
    cloudflared routes to exactly one host port per service, so publishing
    9000 would add nothing for the tunnel and only widen the host surface.
    """
    ports = [str(p) for p in _keycloak_service().get("ports") or []]
    assert ports == ["127.0.0.1:8106:8080"], (
        f"keycloak publishes {ports!r}; expected only 127.0.0.1:8106:8080"
    )


def test_keycloak_bootstraps_the_throwaway_account_only() -> None:
    """The container gets the bootstrap pair and nothing else admin-related.

    Keycloak keeps ``KC_BOOTSTRAP_ADMIN_*`` in the container environment for
    as long as it runs. The services hook deletes the account those values
    create, so they unlock nothing afterwards -- which holds only if the
    username is the one the hook deletes, and only if the permanent admin's
    password never reaches this environment.
    """
    from nexus_deploy.services import KEYCLOAK_BOOTSTRAP_USERNAME

    env = _keycloak_service()["environment"]
    assert env.get("KC_BOOTSTRAP_ADMIN_USERNAME") == KEYCLOAK_BOOTSTRAP_USERNAME, (
        f"KC_BOOTSTRAP_ADMIN_USERNAME is {env.get('KC_BOOTSTRAP_ADMIN_USERNAME')!r}; the "
        f"services hook deletes {KEYCLOAK_BOOTSTRAP_USERNAME!r}, so any other name "
        "would leave a temporary admin behind"
    )
    assert "${KEYCLOAK_BOOTSTRAP_PASSWORD:?" in str(env.get("KC_BOOTSTRAP_ADMIN_PASSWORD")), (
        "KC_BOOTSTRAP_ADMIN_PASSWORD must come from the throwaway bootstrap password"
    )
    compose = (STACKS_DIR / "keycloak" / "docker-compose.yml").read_text()
    code = "\n".join(line.split("#", 1)[0] for line in compose.splitlines())
    assert "KEYCLOAK_ADMIN" not in code, (
        "the permanent admin's credentials must not reach the Keycloak container"
    )


def test_credentials_bundle_leaves_out_what_infisical_leaves_out() -> None:
    """spin-up.yml stores the tofu `secrets` output as the CREDENTIALS_JSON
    Pages secret, minus a list of keys. Anything kept out of Infisical on
    purpose has to be on that list, or the bundle undoes the exclusion.

    The filter is taken from the workflow and run with jq, so this checks
    what the step does rather than what its text looks like.
    """
    import shutil

    if shutil.which("jq") is None:
        pytest.skip("jq is needed to run the workflow's filter")
    workflow = (REPO_ROOT / ".github" / "workflows" / "spin-up.yml").read_text()
    match = re.search(r"""CREDENTIALS=\$\(echo "\$SECRETS_JSON" \| jq -c '([^']*)'\)""", workflow)
    assert match, "spin-up.yml no longer builds CREDENTIALS_JSON with the expected jq filter"
    sample = {
        "infisical_admin_password": "keep-me",
        "keycloak_admin_password": "keep-me-too",
        "keycloak_bootstrap_password": "drop",
        "forgejo_runner_secret": "drop",
        "forgejo_service_token_id": "drop",
        "forgejo_service_token_secret": "drop",
        "empty_value": "",
    }
    out = subprocess.run(
        ["jq", "-c", match.group(1)],
        input=json.dumps(sample),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout) == {
        "infisical_admin_password": "keep-me",
        "keycloak_admin_password": "keep-me-too",
    }


def test_keycloak_hostname_is_a_full_https_url() -> None:
    """KC_HOSTNAME must carry the scheme, not only the host.

    With a bare hostname Keycloak resolves scheme and port from the request,
    and the container only ever sees plain HTTP on 8080. A full URL fixes the
    issuer to https. It is also a precondition for
    KC_HOSTNAME_BACKCHANNEL_DYNAMIC, which the stack sets.
    """
    env = _keycloak_service()["environment"]
    assert str(env.get("KC_HOSTNAME", "")).startswith("https://"), (
        f"KC_HOSTNAME is {env.get('KC_HOSTNAME')!r}; it must be a full https:// URL"
    )
    assert str(env.get("KC_HOSTNAME_BACKCHANNEL_DYNAMIC")) == "true"
    assert env.get("KC_PROXY_HEADERS") == "xforwarded", (
        "without KC_PROXY_HEADERS=xforwarded the backchannel endpoints are "
        "advertised as http:// for requests arriving through the tunnel"
    )


def _mongodb_compose() -> dict[str, Any]:
    """stacks/mongodb/docker-compose.yml, parsed rather than grepped, so a
    commented-out setting cannot satisfy a check."""
    return dict(yaml.safe_load((STACKS_DIR / "mongodb" / "docker-compose.yml").read_text()))


def test_mongodb_is_the_first_service_so_the_firewall_rule_lands_on_it() -> None:
    """The `tcp_ports` override is applied to the FIRST service in the file.

    `firewall.get_compose_first_service` picks the target of the generated
    docker-compose.firewall.yml. Reordering the file so mongo-express comes
    first would publish 27017 on the UI container, where nothing listens:
    the firewall rule opens, the port answers nothing, and the stack looks
    healthy throughout.
    """
    from nexus_deploy.firewall import get_compose_first_service

    first = get_compose_first_service(STACKS_DIR / "mongodb" / "docker-compose.yml")
    assert first == "mongodb", (
        f"the first service in stacks/mongodb/docker-compose.yml is {first!r}; "
        "it must be `mongodb`, or the firewall override publishes 27017 on the wrong container"
    )


def test_mongodb_does_not_publish_the_wire_port_itself() -> None:
    """27017 is published only by the firewall override (#488).

    A `ports:` entry for it in the base file would collide with the override
    on the same host port after the merge, and would also bind the port with
    no firewall toggle behind it.
    """
    ports = _mongodb_compose()["services"]["mongodb"].get("ports") or []
    assert not any("27017" in str(p) for p in ports), (
        f"mongodb publishes {ports!r}; 27017 belongs to the firewall override only"
    )


def test_mongodb_express_has_no_default_login_and_no_shared_network() -> None:
    """mongo-express's image turns basic auth ON with `admin` / `pass`.

    The stack turns it off -- Cloudflare Access is the gate -- which is only
    safe while two things hold: the setting is explicitly `false` (leaving it
    to the image yields the documented default login), and the UI is not on
    app-network, where any container in any stack could drive a root-connected
    UI with no login at all.
    """
    service = _mongodb_compose()["services"]["mongodb-express"]
    env = service["environment"]
    assert str(env.get("ME_CONFIG_BASICAUTH")).lower() == "false", (
        "ME_CONFIG_BASICAUTH must be set explicitly to false; the image defaults "
        "it to true with the credentials admin/pass"
    )
    assert "app-network" not in (service.get("networks") or []), (
        "mongodb-express must stay on mongodb-internal only"
    )
    assert str(env.get("ME_CONFIG_SITE_SESSIONSECRET", "")).startswith(
        "${MONGODB_EXPRESS_SESSION_SECRET:?"
    ), (
        "ME_CONFIG_SITE_SESSIONSECRET must come from the generated secret; "
        "the image default is the literal string `secret`"
    )


def test_kestra_flows_use_no_removed_2x_constructs() -> None:
    """Seeded flows and the rendered system flows must load on Kestra 2.x.

    Two constructs were removed in 2.0 and both were in use here:

    - `io.kestra.plugin.core.flow.ForEach` — gone; `Loop` replaces it and
      takes the same `values` / `concurrencyLimit` / `tasks`, verified
      against 2.0's own plugin schema.
    - `io.kestra.core.models.triggers.types.Schedule` — gone. Kestra 1.0.60
      still accepted it (HTTP 200 on POST) while 2.0 rejects it with
      `422 Could not resolve type id`. The modern
      `io.kestra.plugin.core.trigger.Schedule` is accepted by BOTH, which is
      why this could be fixed without waiting for the version bump.

    Asserted against the flow sources rather than a version string: the point
    is what the flows contain, not which tag they happen to run on.
    """
    import re

    from nexus_deploy.kestra import render_system_flows

    sources = {
        p.name: p.read_text()
        for p in (REPO_ROOT / "examples/workspace-seeds/kestra/flows").glob("*.yaml")
    }
    assert sources, "no seeded Kestra flows found — this test would pass vacuously"
    sources.update(
        render_system_flows(
            repo_owner="owner", repo_name="repo", branch="main", admin_username="a@b.c"
        )
    )

    removed = {
        "ForEach": r"io\.kestra\.plugin\.core\.flow\.ForEach\b",
        "legacy Schedule trigger": r"io\.kestra\.core\.models\.triggers\.types\.Schedule\b",
        # `Loop` runs each iteration as its own sub-execution, so the
        # iteration variables changed and outputs are no longer keyed.
        # Measured on 2.0: `taskrun.value` -> FAILED, `item.value` -> SUCCESS;
        # `outputs.x[item.value].y` -> FAILED, `outputs.x.y` -> SUCCESS.
        "taskrun.* iteration variable": r"\{\{[^}]*\btaskrun\.(value|iteration)\b",
        "output keyed by iteration": r"outputs\.\w+\[[^\]]+\]",
        # Not a 2.0 removal -- `substring` does not exist in 1.0.60 either,
        # so this flow's upload step could never have run. `slice` is the
        # Pebble filter that works on both.
        "substring filter": r"\|\s*substring\(",
    }

    # Comment lines do not count. The flows explain what changed and why,
    # which means they legitimately NAME the removed constructs in prose --
    # and Kestra never sees a comment. Same distinction the SPARK_HADOOP
    # check above draws, for the same reason.
    def code_only(body: str) -> str:
        return "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))

    offenders = [
        f"{name}: {label}"
        for name, body in sources.items()
        for label, pat in removed.items()
        if re.search(pat, code_only(body))
    ]
    assert not offenders, "flows use constructs removed in Kestra 2.0:\n  " + "\n  ".join(offenders)


def test_kestra_flows_parse_as_yaml() -> None:
    """Every seeded flow, and every rendered system flow, must be valid YAML.

    Trivial, and it exists because nothing caught the obvious. Editing a
    comment block in `parallel-http-fetch-to-r2.yaml` left one key indented
    two spaces too far, which makes the file unparseable — and every other
    check in this suite still passed, because they all matched substrings
    rather than loading the document. Kestra would have rejected it at
    registration time, i.e. during a deploy.
    """
    import yaml

    from nexus_deploy.kestra import render_system_flows

    docs = {
        p.name: p.read_text()
        for p in (REPO_ROOT / "examples/workspace-seeds/kestra/flows").glob("*.yaml")
    }
    assert docs, "no seeded Kestra flows found — this test would pass vacuously"
    docs.update(
        render_system_flows(
            repo_owner="owner", repo_name="repo", branch="main", admin_username="a@b.c"
        )
    )

    for name, body in docs.items():
        try:
            parsed = yaml.safe_load(body)
        except yaml.YAMLError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"{name} is not valid YAML: {exc}") from exc
        assert isinstance(parsed, dict), f"{name} did not parse to a mapping"
        for key in ("id", "namespace", "tasks"):
            assert key in parsed, f"{name} has no `{key}`"


def test_kestra_tasks_reach_the_api_internally() -> None:
    """Tasks calling Kestra's own API must not go through the public hostname.

    `git.PushFlows` and `git.SyncFlows` read and write flow definitions over
    Kestra's REST API. Upstream resolves that URL as
    `kestra.tasks.sdk.authentication.url`, then `kestra.url`, then
    `http://localhost:8080`. This stack must set `kestra.url` for the UI's
    absolute links, which means the last fallback is unreachable — so without
    the explicit setting, internal tasks are handed the Cloudflare-Access
    hostname and receive a `302` HTML page instead of JSON. Observed on a live
    deployment: `Failed to export flows from Kestra for namespace <ns>`, with
    an HTML body reading `302 Found ... cloudflare`.

    Parsed from the embedded KESTRA_CONFIGURATION rather than grepped, so a
    commented-out or mis-indented block fails rather than passes.
    """
    import yaml

    compose = yaml.safe_load((REPO_ROOT / "stacks/kestra/docker-compose.yml").read_text())
    cfg = yaml.safe_load(compose["services"]["kestra"]["environment"]["KESTRA_CONFIGURATION"])
    auth = cfg["kestra"]["tasks"].get("sdk", {}).get("authentication", {})

    assert auth.get("url") == "http://localhost:8080", (
        f"tasks.sdk.authentication.url is {auth.get('url')!r}. Anything public "
        "here routes internal API calls into Cloudflare Access."
    )
    # 2.0 also requires those calls to authenticate.
    assert auth.get("username"), "tasks.sdk.authentication.username is unset"
    assert auth.get("password"), "tasks.sdk.authentication.password is unset"
    # The browser-facing URL stays public — the two must not be conflated.
    assert cfg["kestra"]["url"] == "${KESTRA_URL}"


def test_flow_sync_tolerates_an_absent_user_directory() -> None:
    """`sync-user` must not fail when the student has written no flows yet.

    `kestra/flows` is where a student's own flows live. Git cannot store an
    empty directory, so on a fresh workspace it does not exist — and
    SyncFlows' default is to fail on a missing `gitDirectory`. That turns a
    system flow red on every new stack for an entirely normal condition.
    Observed on a live deployment: `sync-seeds` SUCCESS, `sync-user` FAILED,
    "The directory 'kestra/flows' was not found in the git repository". The
    seeds had arrived; only the signal was wrong.

    `sync-seeds` deliberately does NOT get the flag: `nexus_seeds/kestra/flows`
    is written by the seeding phase, so its absence means seeding did not
    happen, and that should stay loud.
    """
    import yaml

    from nexus_deploy.kestra import render_system_flows

    flow = yaml.safe_load(
        render_system_flows(
            repo_owner="owner", repo_name="repo", branch="main", admin_username="a@b.c"
        )["system.flow-sync"]
    )
    tasks = {t["id"]: t for t in flow["tasks"]}
    assert set(tasks) == {"sync-seeds", "sync-user"}, sorted(tasks)

    assert tasks["sync-user"].get("failOnMissingDirectory") is False, (
        "sync-user fails on a fresh workspace without this — the student "
        "directory does not exist until they write their first flow."
    )
    assert "failOnMissingDirectory" not in tasks["sync-seeds"], (
        "sync-seeds must stay loud: a missing seed directory means seeding did not happen."
    )


# ---------------------------------------------------------------------------
# Forgejo Runner: how jobs reach the forge, and what they must not reach (#679)
# ---------------------------------------------------------------------------


def _runner_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "forgejo-runner" / "docker-compose.yml").read_text()))


def _runner_config() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "forgejo-runner" / "runner-config.yml").read_text()))


def _ci_address(service: dict[str, Any]) -> str:
    return str(service["networks"]["forgejo-ci"]["ipv4_address"])


def _ensure_data_dirs_script() -> str:
    from nexus_deploy.setup import _ENSURE_DATA_DIRS_SCRIPT

    return _ENSURE_DATA_DIRS_SCRIPT


def _ci_tls_dir() -> str:
    """Where the CI certificate lives, read from the script that writes
    it rather than repeated here — so renaming it there without moving
    the mounts fails the tests below."""
    script = _ensure_data_dirs_script()
    mount = re.search(r"^MOUNT_POINT=(\S+)", script, re.M)
    tls = re.search(r'^CI_TLS="\$MOUNT_POINT/(\S+?)"', script, re.M)
    assert mount, "ensure_data_dirs no longer declares MOUNT_POINT"
    assert tls, "ensure_data_dirs no longer declares the CI TLS directory"
    return f"{mount.group(1)}/{tls.group(1)}"


def test_forgejo_dind_has_no_tcp_listener() -> None:
    """A job container could drive a TCP listener through its own gateway.

    Measured before the fix: `GET /version` on port 2375 returned 200 from
    inside a job, against a daemon that runs as root with `privileged: true`.
    `dockerd` has to be the first argument: given flags alone, the image's
    entrypoint prepends its default hosts, which include tcp://0.0.0.0:2375.
    """
    dind = _runner_compose()["services"]["forgejo-dind"]
    command = dind["command"]

    assert command[0] == "dockerd", "without `dockerd` first, the entrypoint adds a TCP host"
    hosts = [arg.split("=", 1)[1] for arg in command if arg.startswith("--host=")]
    assert hosts, "dockerd needs an explicit --host, or it falls back to its default"
    assert all(h.startswith("unix://") for h in hosts), hosts
    assert not [arg for arg in command if "tcp://" in arg]
    assert "unix://" in " ".join(dind["healthcheck"]["test"])


def test_forgejo_runner_and_dind_share_the_socket_and_nobody_else_does() -> None:
    services = _runner_compose()["services"]
    dind_host = next(
        a.split("=", 1)[1] for a in services["forgejo-dind"]["command"] if a.startswith("--host=")
    )
    socket_dir = str(Path(dind_host.removeprefix("unix://")).parent)

    assert services["forgejo-runner"]["environment"]["DOCKER_HOST"] == dind_host

    holders = {
        name
        for name, spec in services.items()
        for volume in spec.get("volumes") or []
        if isinstance(volume, str) and volume.split(":")[1] == socket_dir
    }
    assert holders == {"forgejo-dind", "forgejo-runner"}
    # The runner runs as 1001; the socket is group-owned by that gid.
    assert services["forgejo-runner"]["user"] == "1001:1001"
    assert "--group=1001" in services["forgejo-dind"]["command"]


def _runner_instance_url() -> str:
    from nexus_deploy.config import NexusConfig
    from nexus_deploy.infisical import BootstrapEnv
    from nexus_deploy.service_env import _render_forgejo_runner

    rendered = _render_forgejo_runner(NexusConfig(forgejo_runner_secret="0" * 40), BootstrapEnv())
    return str(rendered.env_vars["FORGEJO_INSTANCE_URL"])


def _proxy_conf_code() -> str:
    conf = (STACKS_DIR / "forgejo-runner" / "git-proxy.conf").read_text()
    return "\n".join(line.split("#", 1)[0] for line in conf.splitlines())


def _volume_specs(service: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """``{container path: (host path, mode)}`` for one service's binds."""
    out = {}
    for volume in service.get("volumes") or []:
        if not isinstance(volume, str):
            continue
        parts = volume.split(":")
        out[parts[1]] = (parts[0], parts[2] if len(parts) > 2 else "rw")
    return out


# The variables a job gets, one per client that has to be told where the
# trust store is. There is no single variable all of them read, which is
# why this is a list and not a value.
_CA_ENV_VARS = (
    "GIT_SSL_CAINFO",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
)


def test_forgejo_jobs_resolve_the_forge_to_the_proxy() -> None:
    """Jobs clone from the address the runner is registered with.

    That name does not exist on a job's network — the first Conductor
    deploy failed with `Could not resolve host: forgejo`. The runner maps it
    to forgejo-git-proxy, and the proxy must listen on the registered port,
    with TLS (#888), and forward to the forge.
    """
    services = _runner_compose()["services"]
    options = _runner_config()["container"]["options"]

    url = _runner_instance_url()
    match = re.fullmatch(r"https://([a-z0-9-]+):(\d+)", url)
    assert match, url
    name, port = match.groups()

    assert f"--add-host={name}:{_ci_address(services['forgejo-git-proxy'])}" in options.split()
    # The runner is on this network too and resolves the name through
    # Docker's DNS rather than an --add-host entry.
    assert name in services["forgejo-git-proxy"]["networks"]["forgejo-ci"]["aliases"]

    code = _proxy_conf_code()
    # `ssl` on the listener, not merely the port: without it the
    # certificate below is configuration nobody reads, and every client
    # would be talking cleartext to a port it believes is TLS.
    assert re.search(rf"^\s*listen\s+{port}\s+ssl;", code, re.M)
    assert re.search(r"set\s+\$forge\s+forgejo:3000;", code)
    assert "app-network" in services["forgejo-git-proxy"]["networks"]
    # The healthcheck has to watch the port that is actually served.
    assert port in services["forgejo-git-proxy"]["healthcheck"]["test"][-1]


def test_the_ci_proxy_does_not_answer_for_the_forges_own_name() -> None:
    """One name with two answers, resolved per lookup.

    The runner sits on app-network as well, where `forgejo` is the forge
    itself. Giving the proxy that alias on forgejo-ci would leave the
    runner's own lookups to chance — and the certificate, issued for the
    CI name, would not match half the answers.
    """
    proxy = _runner_compose()["services"]["forgejo-git-proxy"]
    aliases = proxy["networks"]["forgejo-ci"]["aliases"]

    assert "forgejo" not in aliases
    host = re.sub(r"^https://|:\d+$", "", _runner_instance_url())
    assert host != "forgejo"
    # The forge's own name still has to be resolvable from the proxy —
    # that is what it forwards to, over app-network.
    assert re.search(r"set\s+\$forge\s+forgejo:", _proxy_conf_code())


def test_every_job_gets_the_trust_bundle_its_environment_points_at() -> None:
    """The env vars and the mount are one mechanism, in two files.

    Set without the mount, every job gets variables naming a file that is
    not there — measured, as `Ignoring extra certs from
    /nexus-ci/ca-bundle.crt, load failed: No such file or directory`
    followed by a failed checkout, because `valid_volumes` had not been
    widened and the runner dropped the mount without a word.
    """
    config = _runner_config()
    services = _runner_compose()["services"]

    # KeyError here is the point: a client whose variable went missing
    # falls back to the system store, which does not hold our certificate.
    paths = {config["runner"]["envs"][var] for var in _CA_ENV_VARS}
    assert len(paths) == 1, paths
    (bundle_in_job,) = paths

    tokens = shlex.split(config["container"]["options"])
    volumes = [tokens[i + 1] for i, token in enumerate(tokens) if token == "-v"]
    assert len(volumes) == 1, volumes
    source, destination, mode = volumes[0].split(":")
    assert destination == bundle_in_job
    assert mode == "ro"

    # `valid_volumes` governs the volumes in `options` as well, so an
    # empty list silently drops this mount.
    assert config["container"]["valid_volumes"] == [source]

    # The mount's source is resolved by forgejo-dind, not by the host,
    # so that container must hold the file at exactly this path — and
    # read-only, which is what stops a job that asks for `:rw` from
    # rewriting the trust store every later job and the runner use.
    dind = _volume_specs(services["forgejo-dind"])
    assert source in dind, sorted(dind)
    host_path, dind_mode = dind[source]
    assert dind_mode == "ro"
    assert host_path.endswith("/bundle.crt")


def test_the_runner_trusts_the_bundle_it_hands_to_jobs() -> None:
    """Both directions of the runner's own work need it: the forge, whose
    certificate is ours, and data.forgejo.org, where it fetches actions
    from. Go reads SSL_CERT_FILE."""
    runner = _runner_compose()["services"]["forgejo-runner"]

    bundle = runner["environment"]["SSL_CERT_FILE"]
    assert bundle in _volume_specs(runner)
    host_path, mode = _volume_specs(runner)[bundle]
    assert host_path.endswith("/bundle.crt")
    assert mode == "ro"


def test_only_the_ci_proxy_gets_the_private_key() -> None:
    """The key belongs to the process that serves the certificate.

    forgejo-dind runs untrusted code, and the runner has no use for it;
    both get the bundle as a single file, from the same directory.
    """
    services = _runner_compose()["services"]
    tls_dir = _ci_tls_dir()

    for name in ("forgejo-dind", "forgejo-runner"):
        for host_path, _mode in _volume_specs(services[name]).values():
            if host_path.startswith(tls_dir):
                assert host_path == f"{tls_dir}/bundle.crt", (name, host_path)

    proxy = _volume_specs(services["forgejo-git-proxy"])
    code = _proxy_conf_code()
    for kind in ("ssl_certificate", "ssl_certificate_key"):
        match = re.search(rf"^\s*{kind}\s+(\S+);", code, re.M)
        assert match, kind
        mountpoint, filename = match.group(1).rsplit("/", 1)
        assert mountpoint in proxy, match.group(1)
        host_dir, mode = proxy[mountpoint]
        assert (host_dir, mode) == (tls_dir, "ro")
        # And the file nginx names is one the script actually writes,
        # under the variable it holds that directory in.
        assert f'"$CI_TLS/{filename}"' in _ensure_data_dirs_script()


def test_the_ci_certificate_names_the_host_the_runner_registers_with() -> None:
    """A certificate for the wrong name fails every client at once, and
    the material has to exist before compose up: nginx exits on a missing
    ssl_certificate, and Docker turns an absent bind source into a
    directory."""
    script = _ensure_data_dirs_script()
    services = _runner_compose()["services"]

    host = re.sub(r"^https://|:\d+$", "", _runner_instance_url())
    assert f"DNS:{host}" in script
    # The proxy's fixed address as well, for a client that has only the
    # address — the runner's `--add-host` gives jobs the name, but
    # nothing stops a future caller from using the address.
    assert f"IP:{_ci_address(services['forgejo-git-proxy'])}" in script

    # System CAs first, ours appended. A bundle holding only our
    # certificate would break every `uses:` step and every public HTTPS
    # call a job makes, so its absence is fatal rather than a warning.
    system_store = "/etc/ssl/certs/ca-certificates.crt"
    assert system_store in script
    # Anchored on a line that is only `fi`: an unanchored one matches the
    # "fi" inside "ca-certificates" and reads the wrong block, which is
    # how this assertion first failed against code that was correct.
    fatal = re.search(rf"! -r {re.escape(system_store)} \]; then(.*?)^\s*fi$", script, re.S | re.M)
    assert fatal, "the missing-system-store branch is gone"
    assert "exit 1" in fatal.group(1)
    assert re.search(rf"cat {re.escape(system_store)} \"\$CI_TLS/proxy.crt\"", script)


def test_the_ci_certificate_is_replaced_when_its_key_is_gone_or_does_not_match() -> None:
    """nginx refuses to start on a mismatched pair, and the certificate
    alone looks fine — so checking only its expiry would leave the proxy
    dead with nothing regenerating it.

    Reachable from the script itself: the two files are renamed one
    after the other, so a crash in between leaves a new key beside the
    old certificate.
    """
    script = _ensure_data_dirs_script()
    decision = script.split('if [ "$NEED_CERT" -eq 1 ]')[0]

    assert '-s "$CI_TLS/proxy.key"' in decision, "a missing key must force a new pair"
    assert "-pubkey" in decision, "the certificate's public key is never read"
    assert "-pubout" in decision, "the key's public half is never read"
    assert '"$CRT_PUB" != "$KEY_PUB"' in decision


def test_the_ci_trust_bundle_is_rebuilt_on_every_run() -> None:
    """The system CA store is not static: an update adds roots and
    withdraws others. On the snapshot lifecycle this directory outlives
    many such updates, so a bundle kept merely because it exists is a
    trust store frozen at whenever CI was first enabled."""
    script = _ensure_data_dirs_script()

    guards = [
        line
        for line in script.splitlines()
        if line.strip().startswith(("if ", "elif ")) and "bundle.crt" in line
    ]
    assert not guards, guards

    # Written to a temporary name and renamed, so no reader ever sees a
    # half-written trust store.
    assert (
        'cat /etc/ssl/certs/ca-certificates.crt "$CI_TLS/proxy.crt" > "$CI_TLS/bundle.crt.tmp"'
        in (script)
    )
    assert 'mv "$CI_TLS/bundle.crt.tmp" "$CI_TLS/bundle.crt"' in script


def test_the_runner_rewrites_its_credentials_when_the_instance_url_changes() -> None:
    """.runner records the address it was written for and the daemon uses
    that, not the environment. /data outlives the container, so an
    existing file would keep a server on the old http URL indefinitely —
    which is the upgrade path for every stack that already has CI."""
    command = "".join(_runner_compose()["services"]["forgejo-runner"]["command"])

    guard = next(line for line in command.splitlines() if "/data/.runner" in line and "if " in line)
    assert "FORGEJO_INSTANCE_URL" in guard
    # grep reading a file, not a pipe: no early reader to close one (#883).
    assert "|" not in guard.replace("||", "")
    assert "create-runner-file" in command


def test_forgejo_jobs_are_told_the_runners_ci_address_for_the_cache() -> None:
    """Left to guess, the runner may advertise its app-network address,
    which a job cannot reach."""
    services = _runner_compose()["services"]
    assert _runner_config()["cache"]["host"] == _ci_address(services["forgejo-runner"])


def test_forgejo_ci_subnet_holds_the_fixed_addresses_and_avoids_dockers_pools() -> None:
    """A job network inside forgejo-dind is allocated from Docker's default
    pools. If forgejo-ci overlapped one, a job would route the proxy's
    address into its own network."""
    import ipaddress

    compose = _runner_compose()
    subnet = ipaddress.ip_network(compose["networks"]["forgejo-ci"]["ipam"]["config"][0]["subnet"])
    for pool in ("172.16.0.0/12", "192.168.0.0/16"):
        assert not subnet.overlaps(ipaddress.ip_network(pool)), f"{subnet} overlaps {pool}"

    fixed = [
        ipaddress.ip_address(_ci_address(compose["services"][name]))
        for name in ("forgejo-git-proxy", "forgejo-runner")
    ]
    assert all(address in subnet for address in fixed)
    assert len(set(fixed)) == len(fixed)


def test_forgejo_dind_stays_off_app_network() -> None:
    assert _runner_compose()["services"]["forgejo-dind"]["networks"] == ["forgejo-ci"]


# ---------------------------------------------------------------------------
# Cube: semantic layer over the shared postgres, plus its own storage layer
# ---------------------------------------------------------------------------


def _cube_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "cube" / "docker-compose.yml").read_text()))


def test_cube_and_cube_store_are_pinned_in_lockstep() -> None:
    """Upstream ships the two together. A version skew between them is a
    protocol mismatch rather than a feature difference, and it surfaces as
    a query that hangs instead of an image that fails to pull."""
    services = _cube_compose()["services"]

    versions = {}
    for name, key in (("cube", "IMAGE_CUBE"), ("cube-store", "IMAGE_CUBE_STORE")):
        match = re.fullmatch(rf"\$\{{{key}:-[^:]+:(v[0-9.]+)\}}", services[name]["image"])
        assert match, services[name]["image"]
        versions[name] = match.group(1)

    assert versions["cube"] == versions["cube-store"], versions


def test_cube_reaches_cube_store_by_its_service_name() -> None:
    services = _cube_compose()["services"]
    env = services["cube"]["environment"]

    assert env["CUBEJS_CUBESTORE_HOST"] in services, env["CUBEJS_CUBESTORE_HOST"]


def test_cube_does_not_run_the_authentication_bypass() -> None:
    """Cube's Playground is served only in development mode, and upstream
    calls that mode an authentication bypass: it "switches off JWT
    verification on the REST (JSON) and GraphQL APIs", with "use it only on
    a local development machine, never in production".

    Access guards the browser route and never sees in-cluster traffic, so
    dev mode here would mean any container on app-network querying without
    a token — on a server that also hosts CI.
    """
    env = _cube_compose()["services"]["cube"]["environment"]

    assert env["CUBEJS_DEV_MODE"] == "false", (
        "development mode is an authentication bypass; the Playground is not "
        "worth it on a server that runs other people's code"
    )


def test_cube_reads_its_model_from_the_repository_read_only() -> None:
    """A model that lives only in a volume drifts on one server and exists
    nowhere else. stack-sync copies stacks/cube/ on every spin-up, so the
    semantic layer is versioned with the deployment that serves it."""
    cube = _cube_compose()["services"]["cube"]
    mounts = [v for v in cube["volumes"] if isinstance(v, str)]

    model = [v for v in mounts if v.endswith("/cube/conf/model:ro")]
    assert model == ["./model:/cube/conf/model:ro"], mounts
    assert (STACKS_DIR / "cube" / "model").is_dir()


def test_cube_probes_health_with_something_the_image_has() -> None:
    """The image ships neither curl nor wget — measured, after a first draft
    used curl and left the container permanently `unhealthy` with
    `/bin/sh: 1: curl: not found` in every probe. It ships node."""
    check = " ".join(_cube_compose()["services"]["cube"]["healthcheck"]["test"])

    assert "curl" not in check, check
    assert "wget" not in check, check
    assert "node " in check
    assert "/livez" in check


def test_cube_store_writes_into_the_volume_it_mounts() -> None:
    """Its default data directory is /cube/.cubestore, not the /cube/data the
    volume is mounted at — measured. Left implicit, the metastore and cache
    lived in the container layer and every recreate silently discarded
    them."""
    store = _cube_compose()["services"]["cube-store"]
    declared = store["environment"]["CUBESTORE_DATA_DIR"]
    mounts = [v.split(":")[1] for v in store["volumes"] if isinstance(v, str)]

    assert declared in mounts, (declared, mounts)


def test_cube_carries_no_secret_of_its_own() -> None:
    """Both values come from the rendered .env — the compose file names
    them and never holds one."""
    services = _cube_compose()["services"]
    env = services["cube"]["environment"]

    assert env["CUBEJS_DB_PASS"] == "${POSTGRES_PASSWORD}"
    assert env["CUBEJS_API_SECRET"] == "${CUBE_API_SECRET}"
    assert "env_file" in services["cube"]


def test_cube_reads_the_shared_postgres_stack() -> None:
    """It describes tables that already exist; it creates none. The host is
    the shared stack's container name, not a sidecar of its own."""
    services = _cube_compose()["services"]
    env = services["cube"]["environment"]

    assert env["CUBEJS_DB_TYPE"] == "postgres"
    assert env["CUBEJS_DB_HOST"] == "postgres"
    assert env["CUBEJS_DB_USER"] == "nexus-postgres"
    assert "postgres" not in {n for n in services if n != "cube"}, (
        "cube must not bring its own postgres — it reads the shared stack"
    )


# ---------------------------------------------------------------------------
# Apicurio Registry: a single-page UI, its API, and one hostname for both
# ---------------------------------------------------------------------------


def _apicurio_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "apicurio" / "docker-compose.yml").read_text()))


def test_only_the_apicurio_proxy_publishes_a_port() -> None:
    """The UI and the API have to answer under one hostname, which is what
    the proxy is for. A second published port would be a second way in, and
    the API one would sit outside the UI's origin."""
    services = _apicurio_compose()["services"]

    published = {name for name, spec in services.items() if spec.get("ports")}

    assert published == {"apicurio-proxy"}, published


def test_the_apicurio_ui_is_told_a_public_api_url() -> None:
    """The UI reads REGISTRY_API_URL at start, writes it into config.js, and
    the BROWSER calls it — measured. An in-cluster address there produces a
    UI that loads and can reach nothing."""
    env = _apicurio_compose()["services"]["apicurio-ui"]["environment"]

    assert env["REGISTRY_API_URL"].startswith("https://${APICURIO_DOMAIN}"), env
    assert "apicurio:8080" not in env["REGISTRY_API_URL"]


def test_the_apicurio_proxy_routes_the_api_before_the_ui() -> None:
    """nginx picks the longest matching prefix, but the order in the file is
    what a reader checks. `/apis` must reach the registry, `/` the UI."""
    conf = (STACKS_DIR / "apicurio" / "nginx.conf").read_text()

    api = re.search(r"location /apis/ \{[^}]*proxy_pass http://(\w[\w-]*)", conf, re.S)
    ui = re.search(r"location / \{[^}]*proxy_pass http://(\w[\w-]*)", conf, re.S)

    assert api, "no /apis/ location in the proxy config"
    assert api.group(1) == "apicurio"
    assert ui, "no catch-all location in the proxy config"
    assert ui.group(1) == "apicurio-ui"


def test_apicurio_does_not_use_in_memory_storage() -> None:
    """Upstream's own words: "all data is lost when the container image is
    restarted". Every spin-up recreates containers."""
    env = _apicurio_compose()["services"]["apicurio"]["environment"]

    assert env["APICURIO_STORAGE_KIND"] == "sql"
    assert env["APICURIO_STORAGE_SQL_KIND"] == "postgresql"


# ---------------------------------------------------------------------------
# Streamlit: one launcher, two app sources, and the clone that must stay out
# of the scan root
# ---------------------------------------------------------------------------


def _streamlit_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "streamlit" / "docker-compose.yml").read_text()))


def _streamlit_entrypoint() -> str:
    return str(_streamlit_compose()["services"]["streamlit"]["entrypoint"][-1])


def _streamlit_launcher_path(name: str) -> str:
    """The value of a ``<NAME> = Path("...")`` constant in Home.py."""
    source = (STACKS_DIR / "streamlit" / "Home.py").read_text()
    match = re.search(rf'^{name} = Path\("([^"]+)"\)', source, re.M)
    assert match, f"{name} is not declared in Home.py"
    return match.group(1)


def test_the_streamlit_clone_lands_outside_the_examples_root() -> None:
    """The workspace repository holds Kestra flows, marimo notebooks and dbt
    models. If the clone landed under the directory the launcher scans
    recursively, every one of those .py files would be listed as a Streamlit
    app and fail the moment somebody clicked it."""
    examples = PurePosixPath(_streamlit_launcher_path("EXAMPLES_ROOT"))
    workspace = PurePosixPath(_streamlit_launcher_path("WORKSPACE_ROOT"))

    assert not workspace.is_relative_to(examples), (
        f"the workspace clone at {workspace} sits inside the scan root {examples}"
    )
    assert f"{workspace}/" in _streamlit_entrypoint(), (
        "the entrypoint clones somewhere other than WORKSPACE_ROOT"
    )


def test_the_streamlit_entrypoint_expands_its_variables_at_runtime() -> None:
    """A single ``$`` in a compose string is interpolated by Compose when it
    reads the file, from the host's .env — not by the shell in the container.
    Every one of these variables is written to stacks/streamlit/.env for the
    container, so a single ``$`` would silently expand to nothing and the
    clone would be skipped without an error."""
    entrypoint = _streamlit_entrypoint()

    for var in ("FORGEJO_USERNAME", "FORGEJO_PASSWORD", "FORGEJO_REPO_URL", "REPO_NAME"):
        assert not re.search(rf"(?<!\$)\$\{{?{var}", entrypoint), (
            f"${var} in the entrypoint is expanded by Compose, not by the container"
        )
        assert f"$${var}" in entrypoint or f"$${{{var}" in entrypoint, (
            f"{var} is never read by the entrypoint"
        )


def test_the_streamlit_launcher_and_examples_are_mounted_read_only() -> None:
    """Both come from the deployment repository and are re-synced on every
    spin-up. A writable mount would let an edit made through a running app
    survive until the next sync silently overwrote it."""
    volumes = _streamlit_compose()["services"]["streamlit"]["volumes"]

    read_only = {v.split(":")[1] for v in volumes if isinstance(v, str) and v.endswith(":ro")}

    assert "/srv/Home.py" in read_only, volumes
    assert _streamlit_launcher_path("EXAMPLES_ROOT") in read_only, volumes


def test_the_streamlit_launcher_skips_helper_modules() -> None:
    """Underscore-prefixed files are importable helpers, not apps — the same
    convention the marimo seeds use. Without the check, a shared
    `_db.py` would be listed in the sidebar and crash when opened."""
    source = (STACKS_DIR / "streamlit" / "Home.py").read_text()

    assert 'part.startswith((".", "_"))' in source, (
        "Home.py no longer filters dot- and underscore-prefixed path parts"
    )


# ---------------------------------------------------------------------------
# Shiny Server: what ends up in the served directory, and what must not
# ---------------------------------------------------------------------------


def _shiny_compose() -> dict[str, Any]:
    return dict(yaml.safe_load((STACKS_DIR / "shiny" / "docker-compose.yml").read_text()))


def _shiny_entrypoint() -> str:
    return str(_shiny_compose()["services"]["shiny"]["entrypoint"][-1])


def test_the_shiny_workspace_link_is_guarded_on_its_target() -> None:
    """A dangling symlink in `site_dir` takes down the whole index page,
    not just its own entry — measured against a repository with no shiny/
    directory, which is every repository until somebody adds one:

        Invalid application configuration.
        ENOENT: no such file or directory, stat '/srv/shiny-server/workspace'
    """
    entrypoint = _shiny_entrypoint()

    link = re.search(r"^\s*ln -sfn .*/shiny\" (/srv/shiny-server/workspace)$", entrypoint, re.M)
    assert link, "the workspace symlink is no longer created the way this test reads it"

    guard = re.search(r'if \[ -d "/srv/workspace/\$\$\{REPO_NAME:-\}/shiny" \]', entrypoint)
    assert guard, "the symlink is created without checking that its target exists"
    assert guard.start() < link.start(), "the guard runs after the link is created"
    assert "rm -f /srv/shiny-server/workspace" in entrypoint, (
        "a stale link from an earlier start is never removed"
    )


def test_shiny_serves_only_the_workspace_subdirectory() -> None:
    """`site_dir` serves static files as well as apps, so the clone itself
    must stay outside it. Linking the whole repository in would publish
    every file in it — .git included — over HTTP."""
    entrypoint = _shiny_entrypoint()
    volumes = _shiny_compose()["services"]["shiny"]["volumes"]

    assert 'git clone "$$FORGEJO_REPO_URL" "/srv/workspace/$$REPO_NAME"' in entrypoint
    assert not re.search(r'ln -sfn "/srv/workspace/\$\$REPO_NAME" ', entrypoint), (
        "the whole workspace repository is linked into the served directory"
    )
    assert "shiny_workspace:/srv/workspace" in volumes, volumes


def test_shiny_hands_over_to_the_images_own_init() -> None:
    """rocker/shiny runs under s6: a cont-init step copies the container
    environment into Renviron.site, and the service wrapper honours
    APPLICATION_LOGS_TO_STDOUT. Exec'ing the shiny-server binary directly
    starts the server but skips both."""
    entrypoint = _shiny_entrypoint()

    assert entrypoint.rstrip().endswith("exec /init"), entrypoint.rstrip()[-60:]
    assert "exec /usr/bin/shiny-server" not in entrypoint


def test_shiny_installs_r_packages_from_a_dated_snapshot() -> None:
    """`latest` on the Posit Package Manager moves, so a rebuild would
    install versions nothing here was tested against. The dated snapshot
    also still serves Ubuntu binaries, which is what keeps the layer at
    seconds rather than a compile."""
    dockerfile = (STACKS_DIR / "shiny" / "Dockerfile").read_text()

    repo = re.search(r"https://p3m\.dev/cran/__linux__/\w+/(\S+?)'", dockerfile)
    assert repo, "the R package repository is not set the way this test reads it"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", repo.group(1)), (
        f"the p3m snapshot is '{repo.group(1)}', not a date"
    )
