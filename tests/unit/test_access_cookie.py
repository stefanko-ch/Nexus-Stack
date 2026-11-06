"""Every Access application marks its session cookie HttpOnly.

Flowise's sign-in page clears every cookie JavaScript can see. With a
script-visible CF_Authorization that included the Access session: the login
POST then came back as a redirect to the Access login page, the browser
blocked it for CORS, and Flowise rendered a blank page. Any other stack whose
frontend clears cookies the same way would break identically, and nothing at
deploy time would notice, so these tests pin the attribute.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _access_apps(tf: Path) -> dict[str, str]:
    """Body of every `cloudflare_zero_trust_access_application` in a file."""
    text = tf.read_text()
    return {
        m.group(1): m.group(2)
        for m in re.finditer(
            r'resource "cloudflare_zero_trust_access_application" "([^"]+)" \{(.*?)\n\}',
            text,
            re.S,
        )
    }


def test_the_service_apps_set_an_httponly_cookie() -> None:
    apps = _access_apps(REPO_ROOT / "tofu" / "stack" / "main.tf")
    assert "services" in apps, "services Access application not found"
    assert re.search(r"^\s*http_only_cookie_attribute\s*=\s*true\s*$", apps["services"], re.M)


def test_the_control_plane_app_sets_an_httponly_cookie() -> None:
    apps = _access_apps(REPO_ROOT / "tofu" / "control-plane" / "main.tf")
    assert apps, "no Access application found in tofu/control-plane/main.tf"
    for name, body in apps.items():
        assert re.search(r"^\s*http_only_cookie_attribute\s*=\s*true\s*$", body, re.M), name
