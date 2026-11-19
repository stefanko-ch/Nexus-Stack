"""The spin-up smoke check does not pass a dead web port as non-HTTP (#739).

The classifier is the `run:` block of the `Check services answer` step in
spin-up.yml. It runs here for real: `ssh` is a stand-in that prints a probe
report, so the report the classifier reads is chosen by the test.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "spin-up.yml"
SCRIPT = REPO_ROOT / ".github" / "scripts" / "non-http-ports.py"


def _step() -> dict[str, object]:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["spin-up"]["steps"]
    return next(s for s in steps if s.get("name") == "Check services answer")


def _classify(tmp_path: Path, report: str, *, services_yaml: Path | None = None) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ssh").write_text(f"#!/bin/sh\ncat {tmp_path / 'report'}\n")
    (bin_dir / "ssh").chmod(0o755)
    (tmp_path / "report").write_text(report)
    workdir = tmp_path / "repo"
    (workdir / ".github" / "scripts").mkdir(parents=True)
    (workdir / ".github" / "scripts" / "non-http-ports.py").write_text(SCRIPT.read_text())
    (workdir / "services.yaml").write_text(
        (services_yaml or REPO_ROOT / "services.yaml").read_text()
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "REMOTE_PROBE": "unused",
    }
    result = subprocess.run(
        ["bash", "-c", str(_step()["run"])],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_a_web_port_that_answers_no_http_is_faulty(tmp_path: Path) -> None:
    """The Unity Catalog UI case: OOM-killed, nothing bound, proxy accepts."""
    out = _classify(tmp_path, "unity-catalog-ui\t3211\tNOHTTP:52\n")
    assert "FAIL  unity-catalog-ui" in out
    assert "no HTTP answer (curl 52)" in out
    assert "::warning title=smoke-check: unity-catalog-ui::" in out
    assert "0 answering HTTP, 1 faulty, 0 with no HTTP" in out


def test_a_declared_non_http_port_stays_quiet(tmp_path: Path) -> None:
    out = _classify(tmp_path, "postgres\t5432\tNOHTTP:1\n")
    assert "listening, non-HTTP protocol (curl 1)" in out
    assert "0 answering HTTP, 0 faulty, 1 with no HTTP" in out


def test_without_the_port_list_nothing_is_guessed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("not: [a valid\n")
    out = _classify(tmp_path, "unity-catalog-ui\t3211\tNOHTTP:52\n", services_yaml=broken)
    assert "not classified" in out
    assert "Could not build the list of non-HTTP ports" in out
    assert "0 faulty" in out


def test_http_answers_are_still_healthy(tmp_path: Path) -> None:
    out = _classify(tmp_path, "grafana\t3000\t302\nspark\t8088\t200\n")
    assert "2 answering HTTP, 0 faulty" in out


def test_the_port_list_holds_every_tcp_port_and_the_named_extras() -> None:
    out = subprocess.run(
        ["python3", str(SCRIPT), str(REPO_ROOT / "services.yaml")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    ports = {int(p) for p in out}
    services = yaml.safe_load((REPO_ROOT / "services.yaml").read_text())["services"]
    http = {"s3-api", "s3-gateway", "schema-registry", "api"}
    for name, entry in services.items():
        for key, value in (entry.get("tcp_ports") or {}).items():
            if key in http:
                assert int(value) not in ports, f"{name} {key} {value} is HTTP, not excused"
            else:
                assert int(value) in ports, f"{name} tcp_ports {value} missing from the list"
    assert {3901, 7233, 7687, 47335} <= ports


def test_an_unreadable_services_yaml_exits_2(tmp_path: Path) -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), str(tmp_path / "missing.yaml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("port", [3901, 7233, 7687, 47335])
def test_each_named_extra_is_still_published_by_a_compose_file(port: int) -> None:
    """A stale entry would quietly excuse a port someone later reuses for HTTP."""
    published = set()
    for compose_file in (REPO_ROOT / "stacks").glob("*/docker-compose.yml"):
        for service in (
            (yaml.safe_load(compose_file.read_text()) or {}).get("services") or {}
        ).values():
            for mapping in service.get("ports") or []:
                match = re.match(r"^(?:[\d.]+:)?(\d+):", str(mapping).strip('"'))
                if match:
                    published.add(int(match.group(1)))
    assert port in published


@pytest.mark.parametrize(
    ("name", "port"), [("garage", 3900), ("rustfs", 9003), ("redpanda-connect", 4195)]
)
def test_a_dead_s3_or_rest_port_is_faulty(tmp_path: Path, name: str, port: int) -> None:
    """These are firewall ports, but they speak HTTP: silence there is a failure."""
    out = _classify(tmp_path, f"{name}\t{port}\tNOHTTP:52\n")
    assert f"FAIL  {name}" in out


def test_an_unclassified_tcp_port_key_stops_the_list(tmp_path: Path) -> None:
    services = tmp_path / "services.yaml"
    services.write_text(yaml.safe_dump({"services": {"x": {"tcp_ports": {"mystery": 1234}}}}))
    result = subprocess.run(
        ["python3", str(SCRIPT), str(services)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "x.tcp_ports.mystery" in result.stderr
