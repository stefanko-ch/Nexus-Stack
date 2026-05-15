"""Tests for nexus_deploy.firewall.

Covers:
- ``parse_firewall_rules`` shape contract (suffix-strip, empty/null,
  malformed, non-int port)
- ``get_compose_first_service`` order-preservation + missing/empty
  edge cases
- per-service render byte-stable across re-runs (snapshot test on a
  small representative input)
- RedPanda dual-listener mapping (9092→19092, 8081/18081→8081, others
  passthrough) + template substitution + missing-domain error
- ``compile_overrides`` end-to-end on a synthetic stacks/ tree
  (postgres + kestra + redpanda)
- ``write_overrides`` atomicity + per-file failure aggregation
- CLI dispatcher ``firewall configure`` rc=0 / rc=1 / rc=2 contract
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nexus_deploy.firewall import (
    OVERRIDE_FILENAME,
    REDPANDA_DOMAIN_PREFIX,
    REDPANDA_RENDERED_PATH,
    REDPANDA_TEMPLATE_PATH,
    REDPANDA_TEMPLATE_TOKEN,
    CompiledOverride,
    GenerateResult,
    RedpandaArtifacts,
    compile_overrides,
    get_compose_first_service,
    parse_firewall_rules,
    render_compose_override,
    render_redpanda_compose_override,
    render_redpanda_config,
    write_overrides,
)

# ---------------------------------------------------------------------------
# parse_firewall_rules
# ---------------------------------------------------------------------------


def test_parse_strips_index_suffix() -> None:
    """``redpanda-1`` → ``redpanda``, ``kestra-2`` → ``kestra``."""
    raw = json.dumps(
        {
            "redpanda-1": {"port": 9092},
            "redpanda-2": {"port": 8081},
            "kestra-1": {"port": 8080},
        },
    )
    rules = parse_firewall_rules(raw)
    services = sorted({r.service for r in rules})
    assert services == ["kestra", "redpanda"]
    rp_ports = sorted(r.port for r in rules if r.service == "redpanda")
    assert rp_ports == [8081, 9092]


def test_parse_empty_input_is_zero_entry() -> None:
    """Empty/empty-object/null-root all → empty list (Zero Entry mode)."""
    assert parse_firewall_rules("") == []
    assert parse_firewall_rules("{}") == []
    assert parse_firewall_rules("null") == []


def test_parse_malformed_root_raises() -> None:
    """A non-object root (list, string, number) is a hard error."""
    with pytest.raises(ValueError, match="expected JSON object"):
        parse_firewall_rules('["not", "an object"]')
    with pytest.raises(ValueError, match="parse failed"):
        parse_firewall_rules("{not valid json")


def test_parse_skips_pure_suffix_keys() -> None:
    """A key like ``-1`` (empty service after suffix-strip) is skipped
    silently — the legacy bash form ``[ -z \"$service\" ]`` did the
    same when ``jq -r`` produced an empty service portion."""
    raw = json.dumps(
        {
            "-1": {"port": 9092},
            "kestra-1": {"port": 8080},
        },
    )
    rules = parse_firewall_rules(raw)
    assert {r.service for r in rules} == {"kestra"}


def test_parse_skips_non_dict_entries_and_invalid_ports() -> None:
    """Per-key resilience: silently skip entries that don't have a
    parseable ``port`` field — matches the legacy `jq -r` behavior
    that emitted ``null`` for those, then bash's ``[ -z "$service" ]``
    skipped the line."""
    raw = json.dumps(
        {
            "good-1": {"port": 8080},
            "no-port-1": {"otherfield": True},  # no port
            "string-port-1": {"port": "not-a-number"},  # unparseable port
            "null-1": None,  # non-dict entry
            "kestra-1": {"port": 8081},
        },
    )
    rules = parse_firewall_rules(raw)
    services = sorted({r.service for r in rules})
    assert services == ["good", "kestra"]


# ---------------------------------------------------------------------------
# get_compose_first_service
# ---------------------------------------------------------------------------


def test_get_compose_first_service_picks_first_in_insertion_order(
    tmp_path: Path,
) -> None:
    """PyYAML preserves dict insertion order on Python 3.7+ — the
    first key under ``services:`` IS the bash ``services[0]``."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  postgres:\n    image: postgres:16\n  postgres-init:\n    image: alpine\n",
    )
    assert get_compose_first_service(compose) == "postgres"


def test_get_compose_first_service_missing_file_returns_none(
    tmp_path: Path,
) -> None:
    assert get_compose_first_service(tmp_path / "nope.yml") is None


def test_get_compose_first_service_empty_services_returns_none(
    tmp_path: Path,
) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'\nservices: {}\n")
    assert get_compose_first_service(compose) is None


def test_get_compose_first_service_malformed_yaml_returns_none(
    tmp_path: Path,
) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  - not\n  - a\n  - dict\n")
    assert get_compose_first_service(compose) is None


def test_get_compose_first_service_yaml_syntax_error_returns_none(
    tmp_path: Path,
) -> None:
    """A real YAML syntax error (unclosed quote, bad indent) → None.
    Distinct from the previous test which had VALID yaml that just
    parsed to a non-dict shape — this hits the YAMLError branch."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  postgres: {\n    image: 'unclosed\n")
    assert get_compose_first_service(compose) is None


def test_get_compose_first_service_non_dict_root_returns_none(
    tmp_path: Path,
) -> None:
    """A compose file whose top-level is not a mapping (string, list,
    null) → None. Hits the 'isinstance(data, dict)' guard."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("just a plain string at root\n")
    assert get_compose_first_service(compose) is None


def test_get_compose_first_service_unreadable_returns_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read failure (permission denied, transient FS issue) → None,
    not a raised OSError that would crash the whole compile pass."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  postgres:\n    image: postgres\n")

    original_read_text = Path.read_text

    def _raising_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == compose:
            raise OSError("simulated read failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _raising_read_text)
    assert get_compose_first_service(compose) is None


# ---------------------------------------------------------------------------
# render_compose_override
# ---------------------------------------------------------------------------


def test_render_compose_override_single_port() -> None:
    """Single-port mapping shape: ``services.<svc>.ports = [\"p:p\"]``."""
    out = render_compose_override("postgres", [(5432, 5432)])
    assert "services:" in out
    assert "postgres:" in out
    assert "5432:5432" in out


def test_render_compose_override_is_byte_stable() -> None:
    """Same input → same output, twice. Snapshot-friendly invariant
    so re-runs of the firewall step don't churn git diffs from key
    re-ordering."""
    a = render_compose_override("kestra", [(8080, 8080), (8443, 8443)])
    b = render_compose_override("kestra", [(8080, 8080), (8443, 8443)])
    assert a == b


# ---------------------------------------------------------------------------
# render_redpanda_compose_override
# ---------------------------------------------------------------------------


def test_render_redpanda_dual_listener_mapping() -> None:
    """9092 → 19092 (SASL), 8081 → 8081 (SR), 18081 → 8081 (SR alt host),
    everything else → ``p:p``."""
    out = render_redpanda_compose_override([9092, 8081, 18081, 9644])
    assert "9092:19092" in out
    assert "8081:8081" in out
    assert "18081:8081" in out
    # 9644 is "everything else" — passthrough
    assert "9644:9644" in out
    # The internal-only 19092 must NOT appear as a host port mapping
    # (it's only the *container* side of the 9092 mapping).
    assert "19092:19092" not in out


def test_render_redpanda_handles_unsorted_input_deterministically() -> None:
    """Input order doesn't change output — the sort_keys + sorted-set
    pass guarantees determinism for snapshot tests."""
    a = render_redpanda_compose_override([8081, 9092, 18081])
    b = render_redpanda_compose_override([18081, 9092, 8081])
    assert a == b


def test_render_redpanda_dedupes_repeat_ports() -> None:
    """Tofu output sometimes has the same port appearing twice (a
    config copy-paste mistake on the user's side); we dedup so the
    rendered YAML doesn't get a ``9092:19092`` line twice."""
    out = render_redpanda_compose_override([9092, 9092, 9092])
    assert out.count("9092:19092") == 1


# ---------------------------------------------------------------------------
# render_redpanda_config
# ---------------------------------------------------------------------------


def test_render_redpanda_config_substitutes_token() -> None:
    template = (
        "kafka_api:\n"
        "  - address: 0.0.0.0\n"
        "    port: 9092\n"
        "advertised_kafka_api: " + REDPANDA_TEMPLATE_TOKEN + "\n"
    )
    rendered = render_redpanda_config(template, "example.com")
    assert REDPANDA_TEMPLATE_TOKEN not in rendered
    assert f"{REDPANDA_DOMAIN_PREFIX}example.com" in rendered


def test_render_redpanda_config_template_without_token_raises() -> None:
    """R-template-drift (#531 R13): if the template was edited and the
    placeholder token removed/misspelled, str.replace would silently
    emit the template unchanged and RedPanda would advertise a stale
    address. Fail fast instead so the deploy aborts and the operator
    sees that the template needs updating."""
    template_no_token = (
        "kafka_api:\n"
        "  - address: 0.0.0.0\n"
        "    port: 9092\n"
        "advertised_kafka_api: hardcoded.example.com\n"  # no placeholder
    )
    with pytest.raises(ValueError, match="placeholder"):
        render_redpanda_config(template_no_token, "example.com")


def test_render_redpanda_config_empty_domain_raises() -> None:
    """Legacy bash silently skipped on empty $DOMAIN; Python surfaces
    it so the caller can decide whether to skip or abort."""
    template = "advertised_kafka_api: " + REDPANDA_TEMPLATE_TOKEN
    with pytest.raises(ValueError, match="domain is empty"):
        render_redpanda_config(template, "")


# ---------------------------------------------------------------------------
# compile_overrides — end-to-end
# ---------------------------------------------------------------------------


def _make_synthetic_stacks(root: Path, *, with_redpanda_template: bool = True) -> None:
    """Build a minimal stacks/ tree the compile pass can consume."""
    (root / "stacks" / "postgres").mkdir(parents=True)
    (root / "stacks" / "postgres" / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    image: postgres:16\n",
    )
    (root / "stacks" / "kestra").mkdir(parents=True)
    (root / "stacks" / "kestra" / "docker-compose.yml").write_text(
        "services:\n  kestra:\n    image: kestra/kestra:latest\n",
    )
    (root / "stacks" / "redpanda" / "config").mkdir(parents=True)
    (root / "stacks" / "redpanda" / "docker-compose.yml").write_text(
        "services:\n  redpanda:\n    image: redpandadata/redpanda:v23.3.5\n",
    )
    (root / "stacks" / "clickhouse").mkdir(parents=True)
    (root / "stacks" / "clickhouse" / "docker-compose.yml").write_text(
        "services:\n  clickhouse:\n    image: clickhouse/clickhouse-server:25.8\n",
    )
    (root / "stacks" / "rustfs").mkdir(parents=True)
    (root / "stacks" / "rustfs" / "docker-compose.yml").write_text(
        "services:\n  rustfs:\n    image: rustfs/rustfs:1.0.0-alpha\n",
    )
    if with_redpanda_template:
        (root / "stacks" / "redpanda" / REDPANDA_TEMPLATE_PATH).write_text(
            "advertised_kafka_api: " + REDPANDA_TEMPLATE_TOKEN + "\n",
        )


def test_compile_overrides_zero_entry_returns_empty_result(tmp_path: Path) -> None:
    """No firewall rules → ``zero_entry=True``, no compiled artifacts,
    no RedPanda. The CLI maps this to a friendly 'no overrides
    needed' log line."""
    _make_synthetic_stacks(tmp_path)
    result = compile_overrides(
        firewall_json="{}",
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert result.zero_entry is True
    assert result.compiled == ()
    assert result.redpanda is None


def test_compile_overrides_simple_two_services(tmp_path: Path) -> None:
    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps(
        {
            "postgres-1": {"port": 5432},
            "kestra-1": {"port": 8080},
        },
    )
    result = compile_overrides(
        firewall_json=json_str,
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert result.zero_entry is False
    assert len(result.compiled) == 2
    services = sorted(c.service for c in result.compiled)
    assert services == ["kestra", "postgres"]
    assert result.redpanda is None


def test_compile_overrides_redpanda_full_path(tmp_path: Path) -> None:
    """RedPanda firewall ports → both override AND substituted config."""
    _make_synthetic_stacks(tmp_path)
    json_str = json.dumps(
        {
            "redpanda-1": {"port": 9092},
            "redpanda-2": {"port": 8081},
        },
    )
    result = compile_overrides(
        firewall_json=json_str,
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert result.redpanda is not None
    rp = result.redpanda
    assert "9092:19092" in rp.override.yaml_content
    assert "8081:8081" in rp.override.yaml_content
    assert REDPANDA_DOMAIN_PREFIX + "example.com" in rp.config_yaml
    assert REDPANDA_TEMPLATE_TOKEN not in rp.config_yaml


def test_compile_overrides_clickhouse_asymmetric_native_port(tmp_path: Path) -> None:
    """ClickHouse's native protocol listens on container 9000, exposed
    as host 9004. The override must encode this asymmetry — host:host
    would route to a closed container port. Regression test for #488."""
    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps({"clickhouse-1": {"port": 9004}})
    result = compile_overrides(
        firewall_json=json_str,
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert len(result.compiled) == 1
    yaml_content = result.compiled[0].yaml_content
    assert "9004:9000" in yaml_content
    # The naive host:host mapping that was emitted before the fix
    # would have routed firewall traffic to a closed container port.
    assert "9004:9004" not in yaml_content


def test_compile_overrides_rustfs_asymmetric_s3_api_port(tmp_path: Path) -> None:
    """RustFS exposes its S3 API on host 9003 → container 9000 — same
    asymmetric shape as ClickHouse. Without an explicit table entry the
    override would emit '9003:9003', routing firewall traffic to a
    closed container port. Regression test for the second case raised
    in PR #584 review."""
    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps({"rustfs-1": {"port": 9003}})
    result = compile_overrides(
        firewall_json=json_str,
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert len(result.compiled) == 1
    yaml_content = result.compiled[0].yaml_content
    assert "9003:9000" in yaml_content
    assert "9003:9003" not in yaml_content


def test_compile_overrides_non_asymmetric_port_stays_identity(tmp_path: Path) -> None:
    """Stacks not in ASYMMETRIC_PORT_MAPPINGS keep the legacy host:host
    mapping — the asymmetric table is a per-service opt-in, not a
    global behaviour change."""
    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps({"postgres-1": {"port": 5432}})
    result = compile_overrides(
        firewall_json=json_str,
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert "5432:5432" in result.compiled[0].yaml_content


def test_compile_overrides_skips_service_without_compose(tmp_path: Path) -> None:
    """A rule for a service whose ``stacks/<svc>/docker-compose.yml``
    doesn't exist gets recorded in ``skipped`` (matches legacy bash
    behavior of silently dropping such rules)."""
    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps(
        {
            "postgres-1": {"port": 5432},
            "ghost-service-1": {"port": 9999},
        },
    )
    result = compile_overrides(
        firewall_json=json_str,
        stacks_dir=tmp_path,
        domain="example.com",
    )
    assert "ghost-service" in result.skipped
    assert len(result.compiled) == 1
    assert result.compiled[0].service == "postgres"


def test_compile_overrides_redpanda_missing_template_raises(tmp_path: Path) -> None:
    """RedPanda port present but template file missing → hard error,
    not silent skip."""
    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps({"redpanda-1": {"port": 9092}})
    with pytest.raises(FileNotFoundError, match="RedPanda firewall template"):
        compile_overrides(
            firewall_json=json_str,
            stacks_dir=tmp_path,
            domain="example.com",
        )


# ---------------------------------------------------------------------------
# write_overrides — atomic write + failure aggregation
# ---------------------------------------------------------------------------


def test_write_overrides_atomic(tmp_path: Path) -> None:
    """Writes go through mktemp+replace; final files exist with
    expected content; mode is 0o644."""
    target = tmp_path / "stacks" / "postgres" / OVERRIDE_FILENAME
    result = GenerateResult(
        compiled=(
            CompiledOverride(
                service="postgres",
                target_path=target,
                yaml_content="services:\n  postgres:\n    ports:\n    - 5432:5432\n",
            ),
        ),
        redpanda=None,
        zero_entry=False,
    )
    write = write_overrides(result)
    assert target in write.written
    assert target.is_file()
    assert target.read_text() == "services:\n  postgres:\n    ports:\n    - 5432:5432\n"
    mode = target.stat().st_mode & 0o777
    assert mode == 0o644


def test_write_overrides_per_file_failure_aggregation(tmp_path: Path) -> None:
    """A failing write on one file doesn't abort the rest. The
    ``WriteResult`` collects per-file errors so the CLI can emit a
    structured summary instead of crashing on the first OSError."""
    ok_target = tmp_path / "stacks" / "postgres" / OVERRIDE_FILENAME
    # Create a directory where the override file should go — write
    # will fail with IsADirectoryError (an OSError subclass).
    bad_target = tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME
    bad_target.parent.mkdir(parents=True)
    bad_target.mkdir()
    result = GenerateResult(
        compiled=(
            CompiledOverride(
                service="postgres",
                target_path=ok_target,
                yaml_content="services:\n  postgres:\n    ports: ['5432:5432']\n",
            ),
            CompiledOverride(
                service="kestra",
                target_path=bad_target,
                yaml_content="services:\n  kestra:\n    ports: ['8080:8080']\n",
            ),
        ),
        redpanda=None,
        zero_entry=False,
    )
    write = write_overrides(result)
    assert ok_target in write.written
    assert any(p == bad_target for p, _ in write.failed)
    assert not write.is_success


def test_generate_result_is_success_property() -> None:
    """``GenerateResult.is_success`` is always True — compilation
    treats skipped services as warnings, not errors. (Hard failures
    raise; they never reach a GenerateResult instance.) The property
    exists so the CLI can match the standard '<Result>.is_success'
    pattern shared across modules."""
    empty = GenerateResult(compiled=(), redpanda=None, zero_entry=True)
    assert empty.is_success is True
    with_skipped = GenerateResult(
        compiled=(),
        redpanda=None,
        skipped=("ghost-service",),
        zero_entry=False,
    )
    assert with_skipped.is_success is True


def test_write_overrides_redpanda_override_failure_aggregated(
    tmp_path: Path,
) -> None:
    """RedPanda override-write fails (target dir replaced by a
    directory-shaped tree) → ``WriteResult.failed`` records the
    failure, but the rest of the writes (config, non-redpanda
    overrides) still proceed."""
    rp_override_path = tmp_path / "stacks" / "redpanda" / OVERRIDE_FILENAME
    rp_config_path = tmp_path / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
    # Create the override target as a directory so atomic_write fails.
    rp_override_path.parent.mkdir(parents=True)
    rp_override_path.mkdir()
    result = GenerateResult(
        compiled=(),
        redpanda=RedpandaArtifacts(
            override=CompiledOverride(
                service="redpanda",
                target_path=rp_override_path,
                yaml_content="services:\n  redpanda: {ports: ['9092:19092']}\n",
            ),
            config_path=rp_config_path,
            config_yaml="advertised_kafka_api: redpanda-kafka.example.com\n",
        ),
        zero_entry=False,
    )
    write = write_overrides(result)
    assert any(p == rp_override_path for p, _ in write.failed)
    # Config write must STILL succeed despite the override failure.
    assert rp_config_path in write.written
    assert rp_config_path.is_file()


def test_write_overrides_redpanda_config_failure_aggregated(
    tmp_path: Path,
) -> None:
    """RedPanda config-write fails (target replaced by a directory) →
    failure recorded, override write still succeeds."""
    rp_override_path = tmp_path / "stacks" / "redpanda" / OVERRIDE_FILENAME
    rp_config_path = tmp_path / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
    rp_config_path.parent.mkdir(parents=True)
    rp_config_path.mkdir()
    result = GenerateResult(
        compiled=(),
        redpanda=RedpandaArtifacts(
            override=CompiledOverride(
                service="redpanda",
                target_path=rp_override_path,
                yaml_content="services:\n  redpanda: {ports: ['9092:19092']}\n",
            ),
            config_path=rp_config_path,
            config_yaml="advertised_kafka_api: redpanda-kafka.example.com\n",
        ),
        zero_entry=False,
    )
    write = write_overrides(result)
    assert any(p == rp_config_path for p, _ in write.failed)
    assert rp_override_path in write.written
    assert rp_override_path.is_file()


def test_write_overrides_removes_stale_for_removed_service(
    tmp_path: Path,
) -> None:
    """R-stale-cleanup (#531 R1): when an operator removes a firewall
    rule from Tofu (e.g. drops `kestra` from the firewall_rules map),
    the next configure pass MUST delete `stacks/kestra/docker-compose.
    firewall.yml`. Without this, stack-sync rsyncs the stale file to
    the server AND compose_runner keeps `-f`-layering it on every
    `docker compose up` — host port stays exposed even though the
    operator already removed it from Tofu."""
    stale_path = tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text(
        "services:\n  kestra:\n    ports:\n    - 8080:8080\n",
    )
    # Compile a result that has NO kestra rule (operator dropped it).
    other_path = tmp_path / "stacks" / "postgres" / OVERRIDE_FILENAME
    result = GenerateResult(
        compiled=(
            CompiledOverride(
                service="postgres",
                target_path=other_path,
                yaml_content="services:\n  postgres:\n    ports:\n    - 5432:5432\n",
            ),
        ),
        redpanda=None,
        zero_entry=False,
    )
    write_overrides(result, stacks_dir=tmp_path)
    assert not stale_path.exists(), "stale kestra override must be removed"
    assert other_path.is_file(), "non-stale postgres override must remain"


def test_write_overrides_keeps_existing_for_skipped_services(
    tmp_path: Path,
) -> None:
    """R-skipped-not-removed (#531 R5 #1): when ``compile_overrides``
    skips a service because its ``docker-compose.yml`` is missing or
    transiently unparsable, the cleanup pass MUST NOT delete that
    service's existing ``docker-compose.firewall.yml``. Tofu is
    still requesting the firewall rule for it; we just couldn't
    render the override THIS run. Deleting it would silently close
    a still-requested host port on the next deploy."""
    existing = tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME
    existing.parent.mkdir(parents=True)
    existing.write_text(
        "services:\n  kestra:\n    ports:\n    - 8080:8080\n",
    )
    other = tmp_path / "stacks" / "postgres" / OVERRIDE_FILENAME
    # Compile result: kestra was rule-requested but skipped (compose.yml
    # missing/unparsable); postgres compiled successfully.
    result = GenerateResult(
        compiled=(
            CompiledOverride(
                service="postgres",
                target_path=other,
                yaml_content="services:\n  postgres:\n    ports:\n    - 5432:5432\n",
            ),
        ),
        redpanda=None,
        skipped=("kestra",),
        zero_entry=False,
    )
    write_overrides(result, stacks_dir=tmp_path)
    assert existing.exists(), (
        "skipped service's existing override must NOT be removed — Tofu still "
        "requests the rule, we just couldn't render it this run"
    )
    assert other.is_file()


def test_write_overrides_zero_entry_removes_all_existing(tmp_path: Path) -> None:
    """R-zero-entry-cleanup (#531 R1): when firewall_rules is empty
    AFTER previously having entries, ALL pre-existing
    docker-compose.firewall.yml files must be removed. Otherwise the
    operator's 'remove all firewall rules' Tofu apply would have no
    effect on the running deployment."""
    for svc in ("kestra", "postgres", "redpanda"):
        p = tmp_path / "stacks" / svc / OVERRIDE_FILENAME
        p.parent.mkdir(parents=True)
        p.write_text(f"services:\n  {svc}:\n    ports:\n    - 1234:1234\n")
    result = GenerateResult(
        compiled=(),
        redpanda=None,
        zero_entry=True,
    )
    write_overrides(result, stacks_dir=tmp_path)
    for svc in ("kestra", "postgres", "redpanda"):
        assert not (tmp_path / "stacks" / svc / OVERRIDE_FILENAME).exists()


def test_write_overrides_zero_entry_removes_redpanda_config(
    tmp_path: Path,
) -> None:
    """R-zero-entry-redpanda-config (#531 R1): the rendered
    redpanda-firewall.yaml is only valid when RedPanda has firewall
    ports; if all firewall rules are removed, this file must be
    cleaned up too — otherwise setup_redpanda_hook (services.py)
    keeps mounting the external-listener config and RedPanda starts
    advertising `redpanda-kafka.<domain>` even though the firewall
    is closed."""
    rp_config = tmp_path / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
    rp_config.parent.mkdir(parents=True)
    rp_config.write_text("advertised_kafka_api: redpanda-kafka.old.example.com\n")
    result = GenerateResult(compiled=(), redpanda=None, zero_entry=True)
    write_overrides(result, stacks_dir=tmp_path)
    assert not rp_config.exists()


def test_write_overrides_keeps_redpanda_config_when_redpanda_compiled(
    tmp_path: Path,
) -> None:
    """Don't delete the redpanda-firewall.yaml in the same call
    that just (re-)wrote it — the WriteResult tracks it as written;
    cleanup logic must NOT undo writes from the same pass."""
    rp_override = tmp_path / "stacks" / "redpanda" / OVERRIDE_FILENAME
    rp_config = tmp_path / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
    result = GenerateResult(
        compiled=(),
        redpanda=RedpandaArtifacts(
            override=CompiledOverride(
                service="redpanda",
                target_path=rp_override,
                yaml_content="services:\n  redpanda: {ports: ['9092:19092']}\n",
            ),
            config_path=rp_config,
            config_yaml="advertised_kafka_api: redpanda-kafka.example.com\n",
        ),
        zero_entry=False,
    )
    write_overrides(result, stacks_dir=tmp_path)
    assert rp_override.is_file()
    assert rp_config.is_file()
    # Exact-equals on the rendered line — avoids CodeQL's URL-substring
    # pattern (the `"<host>" in <text>` shape, which is meant for code
    # that uses substring as a *sanitization gate*, not a test
    # assertion on hardcoded data). Equivalent verification.
    assert rp_config.read_text() == "advertised_kafka_api: redpanda-kafka.example.com\n"


def test_write_overrides_stale_cleanup_unlink_failure_aggregated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OSError on the stale-cleanup unlink (e.g. concurrent removal,
    permission denied) is aggregated into ``WriteResult.failed`` —
    we don't crash the whole write pass."""
    stale_path = tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("stale\n")

    original_unlink = Path.unlink

    def _raising_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self == stale_path:
            raise OSError("simulated unlink failure")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)

    result = GenerateResult(compiled=(), redpanda=None, zero_entry=True)
    write = write_overrides(result, stacks_dir=tmp_path)
    assert any(p == stale_path and "stale-cleanup" in err for p, err in write.failed)


def test_write_overrides_stale_redpanda_config_unlink_failure_aggregated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OSError on stale redpanda-firewall.yaml unlink → aggregated
    into ``WriteResult.failed``, not raised."""
    rp_config = tmp_path / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
    rp_config.parent.mkdir(parents=True)
    rp_config.write_text("stale: yaml\n")

    original_unlink = Path.unlink

    def _raising_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self == rp_config:
            raise OSError("simulated rp-config unlink failure")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)

    result = GenerateResult(compiled=(), redpanda=None, zero_entry=True)
    write = write_overrides(result, stacks_dir=tmp_path)
    assert any(p == rp_config and "stale-cleanup" in err for p, err in write.failed)


def test_write_overrides_no_stacks_dir_skips_cleanup_pass(tmp_path: Path) -> None:
    """When ``stacks_dir/stacks/`` doesn't exist (e.g. a fresh test
    fixture or a project layout without stacks/), the cleanup pass
    short-circuits without raising. The redpanda-firewall.yaml
    cleanup also depends on the stacks/ tree being present."""
    # tmp_path has no stacks/ subdir
    result = GenerateResult(compiled=(), redpanda=None, zero_entry=True)
    write = write_overrides(result, stacks_dir=tmp_path)
    assert write.is_success
    assert write.written == ()
    assert write.failed == ()


def test_write_overrides_remove_stale_false_skips_cleanup(tmp_path: Path) -> None:
    """``remove_stale=False`` opts out of the cleanup pass — for the
    rare back-compat caller that wants writes-only behaviour."""
    stale_path = tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("stale\n")
    result = GenerateResult(compiled=(), redpanda=None, zero_entry=True)
    write_overrides(result, stacks_dir=tmp_path, remove_stale=False)
    assert stale_path.exists()


def test_write_overrides_includes_redpanda_artifacts(tmp_path: Path) -> None:
    """RedPanda's two artifacts (override + config) both land on disk."""
    override_path = tmp_path / "stacks" / "redpanda" / OVERRIDE_FILENAME
    config_path = tmp_path / "stacks" / "redpanda" / REDPANDA_RENDERED_PATH
    result = GenerateResult(
        compiled=(),
        redpanda=RedpandaArtifacts(
            override=CompiledOverride(
                service="redpanda",
                target_path=override_path,
                yaml_content="services:\n  redpanda:\n    ports: ['9092:19092']\n",
            ),
            config_path=config_path,
            config_yaml="advertised_kafka_api: redpanda-kafka.example.com\n",
        ),
        zero_entry=False,
    )
    write_overrides(result)
    assert override_path.is_file()
    assert config_path.is_file()
    # Exact-equals (see the matching note on the redpanda artifacts test
    # earlier in this file) to keep the assertion outside CodeQL's
    # URL-substring-sanitization pattern.
    assert config_path.read_text() == "advertised_kafka_api: redpanda-kafka.example.com\n"


# ---------------------------------------------------------------------------
# CLI dispatcher (rc contract)
# ---------------------------------------------------------------------------


def test_cli_firewall_configure_zero_entry_returns_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty firewall_rules JSON on stdin → rc=0, no overrides
    written, friendly stderr/stdout message."""
    from nexus_deploy.__main__ import _firewall_configure

    _make_synthetic_stacks(tmp_path)
    monkeypatch.setattr("sys.stdin", _StdinFake("{}"))
    rc = _firewall_configure(["--project-root", str(tmp_path), "--domain", "example.com"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "zero-entry" in out


def test_cli_firewall_configure_zero_entry_with_stale_cleanup_failure_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R-zero-entry-cleanup-failure (#531 R3 #1): zero-entry mode
    with a stale-cleanup unlink failure must return rc=1, NOT rc=0.
    Without this, a failed remote-cleanup leaves the host port
    exposed and the workflow finishes green pretending it closed
    — defeating the whole point of the cleanup pass."""
    from nexus_deploy.__main__ import _firewall_configure

    _make_synthetic_stacks(tmp_path)
    # Pre-create a stale .firewall.yml so the cleanup pass has
    # something to attempt to delete.
    stale = tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME
    stale.write_text("stale\n")

    # Force the unlink to fail.
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self == stale:
            raise OSError("simulated unlink failure")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)
    monkeypatch.setattr("sys.stdin", _StdinFake("{}"))
    rc = _firewall_configure(["--project-root", str(tmp_path), "--domain", "example.com"])
    assert rc == 1, "zero-entry + cleanup failure must return rc=1, not rc=0"
    err = capsys.readouterr().err
    assert "stale-cleanup" in err
    assert "aborting" in err.lower() or "inconsistency" in err.lower()


def test_cli_firewall_configure_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two-service input → both overrides written, rc=0."""
    from nexus_deploy.__main__ import _firewall_configure

    _make_synthetic_stacks(tmp_path, with_redpanda_template=False)
    json_str = json.dumps(
        {
            "postgres-1": {"port": 5432},
            "kestra-1": {"port": 8080},
        },
    )
    monkeypatch.setattr("sys.stdin", _StdinFake(json_str))
    rc = _firewall_configure(["--project-root", str(tmp_path), "--domain", "example.com"])
    assert rc == 0
    assert (tmp_path / "stacks" / "postgres" / OVERRIDE_FILENAME).is_file()
    assert (tmp_path / "stacks" / "kestra" / OVERRIDE_FILENAME).is_file()


def test_cli_firewall_configure_skipped_service_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R-skipped-rc1 (#531 R7 #4): when a service is in firewall_rules
    but its docker-compose.yml is missing/unparseable, the CLI must
    return rc=1 — NOT rc=0. Existing override stays on disk (per the
    R5 #1 safety invariant) but the deployed firewall state may not
    match Tofu if the operator changed the port for that stack.
    Surfacing as rc=1 is the only way the caller can decide to abort
    rather than finishing green on a stale override."""
    from nexus_deploy.__main__ import _firewall_configure

    _make_synthetic_stacks(tmp_path)
    # Remove the kestra compose so it gets skipped, but the firewall
    # rule still references it.
    (tmp_path / "stacks" / "kestra" / "docker-compose.yml").unlink()
    json_str = json.dumps(
        {"kestra-1": {"port": 8080}, "postgres-1": {"port": 5432}},
    )
    monkeypatch.setattr("sys.stdin", _StdinFake(json_str))
    rc = _firewall_configure(["--project-root", str(tmp_path), "--domain", "example.com"])
    assert rc == 1, "skipped service must return rc=1, not rc=0"
    err = capsys.readouterr().err
    assert "skipped" in err
    assert "rc=1" in err or "may not match Tofu" in err


def test_cli_firewall_configure_unknown_arg_returns_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nexus_deploy.__main__ import _firewall_configure

    monkeypatch.setattr("sys.stdin", _StdinFake("{}"))
    rc = _firewall_configure(["--bogus"])
    assert rc == 2
    assert "unknown arg" in capsys.readouterr().err


def test_cli_firewall_configure_malformed_json_returns_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nexus_deploy.__main__ import _firewall_configure

    _make_synthetic_stacks(tmp_path)
    monkeypatch.setattr("sys.stdin", _StdinFake("{not json"))
    rc = _firewall_configure(["--project-root", str(tmp_path), "--domain", "example.com"])
    assert rc == 2
    assert "parse failed" in capsys.readouterr().err


class _StdinFake:
    """Minimal stdin replacement for tests — only ``read()`` is exercised."""

    def __init__(self, content: str) -> None:
        self._content = content

    def read(self) -> str:
        return self._content
