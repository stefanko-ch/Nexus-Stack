"""Firewall override generation.

Generates the per-service docker-compose firewall overrides that
expose TCP ports through the Cloudflare Tunnel. Three responsibilities:

1. **Parse** ``tofu output -json firewall_rules`` into a flat list
   of ``FirewallRule`` entries. The Tofu output uses keys of the
   form ``<service>-<index>`` (e.g. ``redpanda-1``, ``redpanda-2``,
   ``kestra-1``); the ``-<index>`` suffix is stripped during parse so
   one service with N exposed ports yields N rules with the same
   service name.

2. **Render** per-service ``docker-compose.firewall.yml`` overrides.
   Each non-RedPanda service defaults to a ``host:container`` 1:1
   single-listener override. Stacks listed in
   :data:`ASYMMETRIC_PORT_MAPPINGS` get their declared container
   port instead — needed when a stack's daemon listens on a port
   that differs from the host port advertised in
   ``services.yaml``'s ``tcp_ports``. RedPanda gets a dual-listener
   override:
     * 9092 (host) → 19092 (container, SASL listener)
     * 8081 / 18081 (host) → 8081 (container, Schema Registry)
     * everything else: ``p:p``
   PLUS a substituted ``redpanda-firewall.yaml`` produced from
   ``stacks/redpanda/config/redpanda-firewall.yaml.template`` with
   ``__REDPANDA_KAFKA_DOMAIN__`` replaced by ``redpanda-kafka.<domain>``.

3. **Write** the generated artifacts atomically (mktemp + os.replace
   in the target dir) so a partial write from a crashing
   pre-existing run never leaves a half-written compose override on
   disk for the next ``stacks/<svc>/docker-compose.firewall.yml``
   consumer (compose_runner / setup_redpanda_hook).

What's NOT migrated here:

* The ``scp`` loop that copies the generated ``.firewall.yml`` files
  to the server — runs as part of the orchestrator's
  ``firewall-sync`` phase, not here.
* The runtime ``-f docker-compose.firewall.yml`` layering — already
  handled by ``compose_runner.py`` (server-side, on every up).

Public surface:

* :func:`parse_firewall_rules` — JSON → list[FirewallRule]
* :func:`get_compose_first_service` — read docker-compose.yml,
  return the first service name (used as the override target)
* :func:`render_compose_override` — produce override YAML for a
  non-RedPanda service
* :func:`render_redpanda_compose_override` — RedPanda dual-listener
  override
* :func:`render_redpanda_config` — substitute the redpanda.yaml
  template with the real domain
* :func:`compile_overrides` — one-shot: parse + render all
* :func:`write_overrides` — write the compiled artifacts to disk
* :func:`configure` — orchestration helper (compile + write)

The CLI surface lives in :mod:`nexus_deploy.__main__` as
``nexus-deploy firewall configure``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

REDPANDA_TEMPLATE_TOKEN = "__REDPANDA_KAFKA_DOMAIN__"  # noqa: S105 (template placeholder, not a secret)
REDPANDA_DOMAIN_PREFIX = "redpanda-kafka."
COMPOSE_FILENAME = "docker-compose.yml"
OVERRIDE_FILENAME = "docker-compose.firewall.yml"
REDPANDA_TEMPLATE_PATH = "config/redpanda-firewall.yaml.template"
REDPANDA_RENDERED_PATH = "config/redpanda-firewall.yaml"

# Per-(service, host-port) overrides for stacks where the host port
# advertised in ``services.yaml``'s ``tcp_ports`` differs from the
# container port the daemon actually listens on. Default is identity
# (host == container) and matches the legacy bash behaviour. Adding
# an entry here makes the firewall override emit the correct
# ``host:container`` line for that stack; the base ``docker-compose.yml``
# should drop the corresponding ``ports:`` entry at the same time so
# the firewall override is the single source of the host binding (no
# duplicate-host-port merge collision). See GH issue #488.
ASYMMETRIC_PORT_MAPPINGS: dict[tuple[str, int], int] = {
    ("clickhouse", 9004): 9000,
    ("rustfs", 9003): 9000,
}

# Suffix-strip regex: ``-<digits>`` at end of key, e.g. ``redpanda-1`` → ``redpanda``.
_SUFFIX_RE = re.compile(r"-\d+$")


@dataclass(frozen=True)
class FirewallRule:
    """One port-exposure entry from the Tofu output.

    The Tofu output JSON looks like ``{"<svc>-<idx>": {"port": <int>}}``;
    parse strips the ``-<idx>`` suffix so multi-port services produce
    multiple rules with the same ``service`` field.
    """

    service: str
    port: int


@dataclass(frozen=True)
class CompiledOverride:
    """One generated ``docker-compose.firewall.yml`` content + target path."""

    service: str  # stack folder name (e.g. ``"kestra"``)
    target_path: Path  # absolute or stacks-relative path
    yaml_content: str


@dataclass(frozen=True)
class RedpandaArtifacts:
    """Two RedPanda-specific artifacts: the dual-listener compose
    override AND the template-substituted redpanda.yaml."""

    override: CompiledOverride
    config_path: Path  # path of the rendered redpanda-firewall.yaml
    config_yaml: str


@dataclass(frozen=True)
class GenerateResult:
    """Result of :func:`compile_overrides`. ``skipped`` collects services
    where ``docker-compose.yml`` was missing or had no ``services:``
    block — those rules are silently dropped (the legacy bash path
    did the same: ``if [ -n "$FIRST_SERVICE" ]; then ...``)."""

    compiled: tuple[CompiledOverride, ...]
    redpanda: RedpandaArtifacts | None
    skipped: tuple[str, ...] = ()
    zero_entry: bool = False  # True iff the input had no firewall rules

    @property
    def is_success(self) -> bool:
        # Compilation is always "successful" — skipped services are
        # warnings, not errors. The CLI dispatcher maps a hard failure
        # (e.g. unparseable JSON) to a raised exception, not a
        # ``GenerateResult.is_success=False`` field.
        return True


@dataclass(frozen=True)
class WriteResult:
    """Outcome of :func:`write_overrides`. Per-file status is tracked
    so the CLI can warn about a partial-failure rather than silently
    crashing on the first ``OSError``."""

    written: tuple[Path, ...]
    failed: tuple[tuple[Path, str], ...] = ()  # (path, error-message)

    @property
    def is_success(self) -> bool:
        return not self.failed


def parse_firewall_rules(json_str: str) -> list[FirewallRule]:
    """Parse ``tofu output -json firewall_rules``.

    The expected shape::

        {
          "redpanda-1": {"port": 9092, ...},
          "redpanda-2": {"port": 8081, ...},
          "kestra-1":   {"port": 8080, ...}
        }

    The ``-<idx>`` suffix is stripped during parse. Empty input
    (``"{}"`` / ``""`` / null) → empty list (Zero Entry mode). A
    malformed root (not a dict) raises :class:`ValueError`.
    """
    if not json_str.strip():
        return []
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"firewall_rules JSON parse failed: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise ValueError(
            f"firewall_rules: expected JSON object, got {type(raw).__name__}",
        )
    rules: list[FirewallRule] = []
    for key, val in raw.items():
        if not isinstance(val, dict):
            # Skip non-object entries silently — same as legacy `jq -r`
            # which would emit `null` and our `[ -z "$service" ]` skip.
            continue
        port_raw = cast("dict[str, Any]", val).get("port")
        if port_raw is None:
            continue
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            continue
        service = _SUFFIX_RE.sub("", str(key))
        if not service:
            continue
        rules.append(FirewallRule(service=service, port=port))
    return rules


def get_compose_first_service(compose_path: Path) -> str | None:
    """Read the first key under ``services:`` in
    ``stacks/<svc>/docker-compose.yml``. Returns ``None`` if the file
    doesn't exist, can't be parsed, or has no ``services:`` block.

    Matches the legacy bash::

        FIRST_SERVICE=$(python3 -c "
        import yaml
        data = yaml.safe_load(open('stacks/$service/docker-compose.yml'))
        services = list(data.get('services', {}).keys())
        print(services[0] if services else '')
        ")
    """
    if not compose_path.is_file():
        return None
    try:
        text = compose_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        return None
    # Insertion-order from yaml.safe_load (PyYAML preserves dict order
    # since Python 3.7+) → first key matches the bash `services[0]`.
    first = next(iter(services))
    return str(first)


def render_compose_override(first_service: str, port_mappings: list[tuple[int, int]]) -> str:
    """Build the ``docker-compose.firewall.yml`` content for a
    non-RedPanda service.

    Each mapping is ``(host_port, container_port)``; the legacy bash
    rendered ``p:p`` only (host=container), but we accept the
    explicit pair to share the renderer with the RedPanda path
    (which differs).

    Output is dumped via PyYAML's ``default_flow_style=False`` to
    match the legacy bash form (block-style), with ``sort_keys=False``
    so ``services`` → ``<svc>`` → ``ports`` ordering is stable across
    re-renders (snapshot-friendly invariant).
    """
    payload: dict[str, Any] = {
        "services": {
            first_service: {
                "ports": [f"{host}:{container}" for host, container in port_mappings],
            },
        },
    }
    return yaml.dump(payload, default_flow_style=False, sort_keys=False)


def render_redpanda_compose_override(host_ports: list[int]) -> str:
    """RedPanda's dual-listener override — different mapping rules
    per port. Mirrors the legacy ``PORTS_LIST`` builder::

        host  9092 → container 19092 (external SASL listener)
        host  8081 → container  8081 (Schema Registry)
        host 18081 → container  8081 (Schema Registry, alt host port)
        any other  → ``p:p``

    The list of host ports is sorted before rendering so the output
    is deterministic regardless of input order.
    """
    mappings: list[tuple[int, int]] = []
    for p in sorted(set(host_ports)):
        if p == 9092:
            mappings.append((9092, 19092))
        elif p in (8081, 18081):
            mappings.append((p, 8081))
        else:
            mappings.append((p, p))
    return render_compose_override("redpanda", mappings)


def render_redpanda_config(template_text: str, domain: str) -> str:
    """Substitute the ``__REDPANDA_KAFKA_DOMAIN__`` placeholder with
    ``redpanda-kafka.<domain>``. Mirrors::

        sed "s/__REDPANDA_KAFKA_DOMAIN__/redpanda-kafka.$DOMAIN/g" template

    A missing ``domain`` (empty string) raises ``ValueError`` — the
    legacy bash skipped silently when ``$DOMAIN`` was empty (the
    surrounding ``if [ -n "$DOMAIN" ]`` gate), but the Python path
    surfaces the error so the caller can decide whether to skip.

    Also raises ``ValueError`` when the template doesn't contain the
    expected placeholder token. ``str.replace`` would silently emit
    the template unchanged in that case, and RedPanda would advertise
    a stale / unrendered ``advertised_kafka_api`` value at startup —
    silent template-drift breakage. Fail fast on the deploy so the
    operator knows the template needs updating.
    """
    if not domain:
        raise ValueError(
            "render_redpanda_config: domain is empty; refusing to substitute "
            f"{REDPANDA_TEMPLATE_TOKEN!r} with a malformed value",
        )
    if REDPANDA_TEMPLATE_TOKEN not in template_text:
        raise ValueError(
            f"render_redpanda_config: template doesn't contain the expected "
            f"placeholder {REDPANDA_TEMPLATE_TOKEN!r}. Either the template at "
            f"{REDPANDA_TEMPLATE_PATH} was edited and the token removed/"
            f"misspelled, or this code's REDPANDA_TEMPLATE_TOKEN drifted from "
            f"the template. Refusing to write an unsubstituted config that "
            f"would make RedPanda advertise a wrong external address.",
        )
    replacement = f"{REDPANDA_DOMAIN_PREFIX}{domain}"
    return template_text.replace(REDPANDA_TEMPLATE_TOKEN, replacement)


def compile_overrides(
    *,
    firewall_json: str,
    stacks_dir: Path,
    domain: str,
) -> GenerateResult:
    """Parse + render all firewall-override artifacts.

    Pure-logic (no writes). Reads ``stacks/<svc>/docker-compose.yml``
    + the RedPanda template if applicable. Returns a
    :class:`GenerateResult` the caller writes to disk via
    :func:`write_overrides`.
    """
    rules = parse_firewall_rules(firewall_json)
    if not rules:
        return GenerateResult(compiled=(), redpanda=None, zero_entry=True)

    # Group ports per non-redpanda service; track redpanda ports separately.
    by_service: dict[str, list[int]] = {}
    redpanda_ports: list[int] = []
    for rule in rules:
        if rule.service == "redpanda":
            redpanda_ports.append(rule.port)
        else:
            by_service.setdefault(rule.service, []).append(rule.port)

    compiled: list[CompiledOverride] = []
    skipped: list[str] = []
    for service, ports in by_service.items():
        compose_path = stacks_dir / "stacks" / service / COMPOSE_FILENAME
        first_service = get_compose_first_service(compose_path)
        if first_service is None:
            skipped.append(service)
            continue
        # Default to identity host:container mapping (legacy bash
        # behaviour). Stacks listed in ASYMMETRIC_PORT_MAPPINGS get
        # their declared container port — needed for any stack whose
        # base compose maps host:container asymmetrically.
        mappings = [(p, ASYMMETRIC_PORT_MAPPINGS.get((service, p), p)) for p in sorted(set(ports))]
        yaml_content = render_compose_override(first_service, mappings)
        target = stacks_dir / "stacks" / service / OVERRIDE_FILENAME
        compiled.append(
            CompiledOverride(
                service=service,
                target_path=target,
                yaml_content=yaml_content,
            ),
        )

    redpanda: RedpandaArtifacts | None = None
    if redpanda_ports:
        # Domain MUST be present for RedPanda — the redpanda.yaml
        # template needs it for `advertised_kafka_api`. The legacy
        # bash gated the whole RedPanda branch on `if [ -n "$DOMAIN" ]`;
        # we surface the missing-domain case as a ValueError instead
        # of silently skipping.
        template_path = stacks_dir / "stacks" / "redpanda" / REDPANDA_TEMPLATE_PATH
        try:
            template_text = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FileNotFoundError(
                f"RedPanda firewall template missing: {template_path}",
            ) from exc
        config_yaml = render_redpanda_config(template_text, domain)
        override_yaml = render_redpanda_compose_override(redpanda_ports)
        redpanda = RedpandaArtifacts(
            override=CompiledOverride(
                service="redpanda",
                target_path=stacks_dir / "stacks" / "redpanda" / OVERRIDE_FILENAME,
                yaml_content=override_yaml,
            ),
            config_path=stacks_dir / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH,
            config_yaml=config_yaml,
        )

    return GenerateResult(
        compiled=tuple(compiled),
        redpanda=redpanda,
        skipped=tuple(skipped),
        zero_entry=False,
    )


def _atomic_write(path: Path, content: str) -> None:
    """mktemp-in-target-dir + ``os.replace`` so a crash mid-write
    never leaves a half-written compose override on disk.

    Same pattern as ``setup.configure_ssh``: tmpfile in the same
    directory (so ``replace`` is atomic), explicit ``fchmod`` to
    drop the umask race window, then atomic rename.
    """
    import contextlib

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        tmp_path.chmod(0o644)
        tmp_path.replace(path)
    except Exception:
        # Best-effort cleanup; if mktemp gave us the fd but the
        # atomic-replace failed, leave no orphan tmpfile behind.
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def write_overrides(
    result: GenerateResult,
    *,
    stacks_dir: Path | None = None,
    remove_stale: bool = True,
) -> WriteResult:
    """Atomic-write each compiled artifact to its target path, then
    (when ``remove_stale=True``, the default) delete any
    ``docker-compose.firewall.yml`` files belonging to services NOT
    present in ``result.compiled`` — including ALL of them when
    ``zero_entry=True``.

    Without this cleanup, removing a firewall rule from Tofu would
    NOT actually remove the host port mapping on the next deploy:
    the stale ``stacks/<svc>/docker-compose.firewall.yml`` would
    still be on disk, ``stack-sync`` would still rsync it to the
    server, and ``compose_runner`` would still layer it onto every
    ``docker compose up`` via ``-f docker-compose.firewall.yml``.
    The legacy bash had the same hole; this migration plugs it.

    RedPanda's two artifacts (``docker-compose.firewall.yml`` AND the
    rendered ``config/redpanda-firewall.yaml``) are both removed when
    RedPanda has no firewall ports — leaving the rendered yaml in
    place would keep ``setup_redpanda_hook`` (services.py) running
    in firewall-mode after the operator already removed the rules.

    ``stacks_dir`` is required for the cleanup pass to know where to
    walk; if None, the cleanup is skipped (back-compat for a caller
    that only wants the writes). The CLI always passes it.
    """
    written: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for c in result.compiled:
        try:
            _atomic_write(c.target_path, c.yaml_content)
            written.append(c.target_path)
        except OSError as exc:
            failed.append((c.target_path, str(exc)))

    if result.redpanda is not None:
        rp = result.redpanda
        try:
            _atomic_write(rp.override.target_path, rp.override.yaml_content)
            written.append(rp.override.target_path)
        except OSError as exc:
            failed.append((rp.override.target_path, str(exc)))
        try:
            _atomic_write(rp.config_path, rp.config_yaml)
            written.append(rp.config_path)
        except OSError as exc:
            failed.append((rp.config_path, str(exc)))

    if remove_stale and stacks_dir is not None:
        kept = {c.target_path for c in result.compiled}
        if result.redpanda is not None:
            kept.add(result.redpanda.override.target_path)
        # ``skipped`` services (compose.yml missing or transiently
        # unparsable at compile time) MUST be excluded from cleanup
        # too — Tofu is still requesting the firewall rule for them,
        # we just couldn't render the override THIS run. Removing the
        # existing .firewall.yml in that case would silently close a
        # still-requested host port on the next deploy. The legacy
        # bash didn't have this hole because it never had a stale-
        # cleanup pass at all; my R1 cleanup added it but the first
        # implementation conflated 'skipped' with 'removed'.
        skipped_targets = {
            stacks_dir / "stacks" / svc / OVERRIDE_FILENAME for svc in result.skipped
        }
        # Walk every stack directory and unlink any
        # docker-compose.firewall.yml that isn't in the compiled
        # write set AND isn't owned by a skipped service (i.e. either
        # zero-entry mode OR the operator actually removed this
        # specific service's firewall rule from Tofu).
        stacks_root = stacks_dir / "stacks"
        if stacks_root.is_dir():
            for stale in stacks_root.glob(f"*/{OVERRIDE_FILENAME}"):
                if stale in kept or stale in skipped_targets:
                    continue
                try:
                    stale.unlink()
                except OSError as exc:
                    failed.append((stale, f"stale-cleanup: {exc}"))
        # The rendered redpanda-firewall.yaml only exists when there
        # WERE redpanda firewall ports; if there aren't anymore, drop
        # it so setup_redpanda_hook doesn't keep using the stale
        # external-listener config.
        if result.redpanda is None:
            redpanda_config = stacks_dir / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
            if redpanda_config.is_file():
                try:
                    redpanda_config.unlink()
                except OSError as exc:
                    failed.append((redpanda_config, f"stale-cleanup: {exc}"))

    return WriteResult(written=tuple(written), failed=tuple(failed))


def configure(
    *,
    firewall_json: str,
    stacks_dir: Path,
    domain: str,
) -> tuple[GenerateResult, WriteResult]:
    """One-shot orchestration: compile + write + stale-cleanup.

    Even in ``zero_entry`` mode we still call :func:`write_overrides`
    (with an empty ``compiled`` set) so the stale-cleanup pass runs
    — that's the whole point: a previously-non-empty firewall_rules
    that's now empty MUST trigger removal of the stale .yml files,
    otherwise the host port mappings persist on the next deploy.
    """
    gen = compile_overrides(
        firewall_json=firewall_json,
        stacks_dir=stacks_dir,
        domain=domain,
    )
    write = write_overrides(gen, stacks_dir=stacks_dir)
    return gen, write


__all__ = [
    "COMPOSE_FILENAME",
    "OVERRIDE_FILENAME",
    "REDPANDA_DOMAIN_PREFIX",
    "REDPANDA_RENDERED_PATH",
    "REDPANDA_TEMPLATE_PATH",
    "REDPANDA_TEMPLATE_TOKEN",
    "CompiledOverride",
    "FirewallRule",
    "GenerateResult",
    "RedpandaArtifacts",
    "WriteResult",
    "compile_overrides",
    "configure",
    "get_compose_first_service",
    "parse_firewall_rules",
    "render_compose_override",
    "render_redpanda_compose_override",
    "render_redpanda_config",
    "write_overrides",
]
