#!/usr/bin/env python3
"""Print the host ports that legitimately speak something other than HTTP.

Used by the smoke check in spin-up.yml (#739). A published port that accepts
a connection but does not answer HTTP is healthy for a database, a broker or
SFTP, and dead for a web UI whose process never bound its port: Docker's
userland proxy accepts the connection either way. The check cannot tell the
two apart by probing, so it asks this list. A port in it is "listening,
non-HTTP"; any other port that does not answer HTTP is reported as faulty.

The list is the `tcp_ports` values in services.yaml whose protocol is not
HTTP (Postgres wire, Kafka, CQL, SFTP, ...; the S3 APIs and REST endpoints
there are HTTP and stay off it), plus the few non-HTTP ports a compose file
publishes by itself, named below.

Usage: non-http-ports.py [services.yaml]   -> one port per line, sorted.
Exit status 2 when services.yaml cannot be read or names a tcp_ports key
this script does not classify, so the caller can tell "no such ports"
from "could not build the list".
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Published directly by a stack's compose file, not through tcp_ports, and
# not HTTP. tests/unit/test_smoke_check.py checks each is still published.
COMPOSE_PUBLISHED_NON_HTTP: dict[int, str] = {
    3901: "garage: RPC between Garage nodes",
    7233: "temporal: frontend gRPC",
    7687: "neo4j: Bolt protocol",
    47335: "mindsdb: MySQL wire protocol",
}


# `tcp_ports` keys, by protocol. Not every firewall port is non-HTTP: an S3
# API, a schema registry and a REST API speak HTTP, so a dead one must stay
# a failure rather than be excused. A key in neither set is an error, so a
# new tcp_ports entry forces the question.
NON_HTTP_TCP_KEYS = frozenset(
    {"native", "cql", "wire", "pgducklake", "postgres", "kafka", "sftp", "timescaledb"}
)
HTTP_TCP_KEYS = frozenset({"s3-api", "s3-gateway", "schema-registry", "api"})


class UnclassifiedPortError(Exception):
    """A tcp_ports key that is in neither protocol set."""


def non_http_ports(services: dict[str, dict[str, object]]) -> list[int]:
    ports = set(COMPOSE_PUBLISHED_NON_HTTP)
    for name, entry in services.items():
        tcp = entry.get("tcp_ports") or {}
        if not isinstance(tcp, dict):
            continue
        for key, value in tcp.items():
            if key in NON_HTTP_TCP_KEYS:
                ports.add(int(value))
            elif key not in HTTP_TCP_KEYS:
                raise UnclassifiedPortError(f"{name}.tcp_ports.{key}")
    return sorted(ports)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("services.yaml")
    try:
        services = yaml.safe_load(path.read_text())["services"]
    except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        print(f"non-http-ports: cannot read {path}: {type(exc).__name__}", file=sys.stderr)
        return 2
    try:
        ports = non_http_ports(services)
    except UnclassifiedPortError as exc:
        print(f"non-http-ports: {exc} is neither HTTP nor non-HTTP here; add it", file=sys.stderr)
        return 2
    print("\n".join(str(p) for p in ports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
