#!/usr/bin/env python3
"""Print the host ports that legitimately speak something other than HTTP.

Used by the smoke check in spin-up.yml (#739). A published port that accepts
a connection but does not answer HTTP is healthy for a database, a broker or
SFTP, and dead for a web UI whose process never bound its port: Docker's
userland proxy accepts the connection either way. The check cannot tell the
two apart by probing, so it asks this list. A port in it is "listening,
non-HTTP"; any other port that does not answer HTTP is reported as faulty.

The list is every `tcp_ports` value in services.yaml (what the firewall
override publishes: Postgres wire, Kafka, SFTP, S3 SDK endpoints, ...) plus
the few non-HTTP ports a compose file publishes by itself, named below.

Usage: non-http-ports.py [services.yaml]   -> one port per line, sorted.
Exit status 2 when services.yaml cannot be read, so the caller can tell
"no such ports" from "could not build the list".
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


def non_http_ports(services: dict[str, dict[str, object]]) -> list[int]:
    ports = set(COMPOSE_PUBLISHED_NON_HTTP)
    for entry in services.values():
        tcp = entry.get("tcp_ports") or {}
        if isinstance(tcp, dict):
            for value in tcp.values():
                ports.add(int(value))  # type: ignore[call-overload]
    return sorted(ports)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("services.yaml")
    try:
        services = yaml.safe_load(path.read_text())["services"]
    except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        print(f"non-http-ports: cannot read {path}: {type(exc).__name__}", file=sys.stderr)
        return 2
    print("\n".join(str(p) for p in non_http_ports(services)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
