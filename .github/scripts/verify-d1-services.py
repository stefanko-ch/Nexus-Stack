#!/usr/bin/env python3
"""Compare the services in D1 with services.yaml, after the sync.

Usage: verify-d1-services.py <wrangler-json-file> <services.yaml>

The first file holds what `wrangler d1 execute --json --command "SELECT name
FROM services"` printed on stdout. Exit status:

  0  every service in services.yaml is in D1
  1  some are missing: the sync wrote fewer rows than it should have
  2  the answer could not be read, so nothing is known either way; the
     sync script fails on this too, because this check is its only gate

The check this replaces printed "✅ Found 0 services in D1" after a sync that
had written every row (#943). It read `.result | length` from a document that
is an array, `jq` failed, and `|| echo "0"` turned the failure into a count.
A check that cannot read its input must say that, not report a number.

D1 may hold more rows than services.yaml: the sync never deletes, so a
service removed from the file keeps its row. Only a shortfall is an error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

OK, MISSING, UNREADABLE = 0, 1, 2


def names_in_d1(document: object) -> list[str]:
    """The `name` column from wrangler's JSON, or raise ValueError.

    `wrangler d1 execute --json` prints one object per statement, each with a
    `results` list. A single object of that shape is accepted too.
    """
    statements = document if isinstance(document, list) else [document]
    if not statements:
        raise ValueError("the answer is an empty list")
    names: list[str] = []
    for statement in statements:
        if not isinstance(statement, dict) or not isinstance(statement.get("results"), list):
            raise ValueError("no `results` list in the answer")
        # A statement that reports failure can still carry a `results` list.
        # Its rows say nothing about the table.
        if statement.get("success") is not True:
            raise ValueError("a statement in the answer does not report success")
        for row in statement["results"]:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                raise ValueError("a row without a `name`")
            names.append(row["name"])
    return names


def verify(wrangler_json: str, services_yaml: str) -> tuple[int, str]:
    """Compare wrangler's answer with services.yaml.

    Returns the exit status (OK, MISSING or UNREADABLE) and the one line to
    print. Only OK carries the tick.
    """
    try:
        expected = sorted(yaml.safe_load(services_yaml)["services"])
    except (yaml.YAMLError, KeyError, TypeError) as error:
        return UNREADABLE, f"⚠️ Could not read services.yaml to compare against: {error}"
    try:
        present = set(names_in_d1(json.loads(wrangler_json)))
    except (json.JSONDecodeError, ValueError) as error:
        return UNREADABLE, (
            f"⚠️ Could not read the service list D1 returned, so the sync is NOT verified: {error}"
        )
    missing = [name for name in expected if name not in present]
    if missing:
        shown = ", ".join(missing[:10]) + (" …" if len(missing) > 10 else "")
        return MISSING, (
            f"❌ D1 is missing {len(missing)} of {len(expected)} services "
            f"from services.yaml: {shown}"
        )
    return OK, (
        f"✅ All {len(expected)} services from services.yaml are in D1 "
        f"(D1 holds {len(present)} rows)"
    )


def main(argv: list[str]) -> int:
    """Read the two files named in ``argv``, print the verdict, return the status."""
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return UNREADABLE
    try:
        answer, services = Path(argv[1]).read_text(), Path(argv[2]).read_text()
    except (OSError, UnicodeDecodeError) as error:
        # No answer to read is "cannot tell", not "services are missing".
        print(
            f"  ⚠️ Could not read the check's input, so the sync is NOT verified: {error}",
            file=sys.stderr,
        )
        return UNREADABLE
    status, message = verify(answer, services)
    print(f"  {message}", file=sys.stdout if status == OK else sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
