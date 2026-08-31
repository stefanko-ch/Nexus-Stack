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

import re
from pathlib import Path
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
        if "postgres" not in image or "postgrest" in image or "ducklake" in image:
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
            major_match = re.search(r"postgres:(\d+)", image)
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
