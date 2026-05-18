"""OpenTofu CLI wrapper for nexus_deploy.

:class:`TofuRunner` is a thin typed wrapper around ``tofu output``
with explicit per-call default handling: callers pass ``default=...``
to opt into the silent-fallback semantic, omit it to require a
successful read.

``TofuRunner`` also carries :meth:`TofuRunner.state_list_ok` and
:meth:`TofuRunner.diagnose_state` for the pre-flight ``tofu state
list`` check the pipeline runs before any output reads. Outside the
class, the module exports :func:`load_r2_credentials` +
:class:`R2Credentials` for parsing ``tofu/.r2-credentials`` (the
shell-format AWS-creds file the R2 backend expects).

``tofu apply`` is intentionally NOT wrapped here — that runs in the
orchestrator's pre-bootstrap pipeline so streaming-output and
per-stage logging concerns live next to where they're consumed.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, overload

# Sentinel for "default not supplied" — distinguishes "caller passed
# default=None" (use None on failure) from "caller passed nothing"
# (raise TofuError on failure). Plain ``None`` won't do; the legacy
# bash uses an empty-string default in some places and json `{}` /
# `0` in others, all of which are valid user-supplied defaults.
_MISSING: Final = object()


class TofuError(Exception):
    """Raised when ``tofu output`` fails AND no default was supplied."""


class TofuRunner:
    """Run ``tofu output`` in a fixed working directory.

    The default ``tofu_dir`` is ``tofu/stack`` (the canonical state
    directory). Pass an explicit path for tests or when wrapping the
    secondary ``tofu/control-plane`` state.
    """

    def __init__(self, tofu_dir: Path = Path("tofu/stack")) -> None:
        self.tofu_dir = tofu_dir

    @overload
    def output_raw(self, name: str) -> str: ...
    @overload
    def output_raw(self, name: str, *, default: str) -> str: ...

    def output_raw(self, name: str, *, default: Any = _MISSING) -> str:
        """``tofu output -raw <name>``.

        Pass ``default=""`` for the silent-fallback semantic; omit
        ``default`` to make a missing/erroring output raise
        :class:`TofuError`.
        """
        try:
            completed = subprocess.run(
                ["tofu", "output", "-raw", name],
                cwd=self.tofu_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            if default is _MISSING:
                raise TofuError(f"tofu output -raw {name} failed in {self.tofu_dir}") from exc
            return str(default)
        # Strip trailing newlines to match the POSIX $(...) command-
        # substitution semantic that callers expect: $() removes ALL
        # trailing newlines, so `SERVER_IP=$(tofu output -raw server_ip)`
        # lands without the `\n`. Returning raw stdout would diverge
        # subtly: `f"http://{server_ip}/api"` becomes
        # `"http://1.2.3.4\n/api"` — silent breakage downstream.
        return completed.stdout.rstrip("\n")

    @overload
    def output_json(self, name: str) -> Any: ...
    @overload
    def output_json(self, name: str, *, default: Any) -> Any: ...

    def output_json(self, name: str, *, default: Any = _MISSING) -> Any:
        """``tofu output -json <name>``, parsed.

        Three failure modes are collapsed into ``default`` when
        provided: tofu binary missing, tofu exited non-zero, stdout
        not valid JSON. Without ``default`` any of those raise
        :class:`TofuError`.
        """
        try:
            completed = subprocess.run(
                ["tofu", "output", "-json", name],
                cwd=self.tofu_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            if default is _MISSING:
                raise TofuError(f"tofu output -json {name} failed in {self.tofu_dir}") from exc
            return default
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            if default is _MISSING:
                raise TofuError(f"tofu output -json {name} returned non-JSON stdout") from exc
            return default

    def state_list_ok(self) -> bool:
        """Return True iff ``tofu state list`` exits 0.

        Convenience wrapper around :meth:`diagnose_state` for callers
        that only need a yes/no signal (the existing ``test_tofu.py``
        contract). New callers that want to surface a failure reason
        to the operator should use :meth:`diagnose_state` directly.
        """
        return self.diagnose_state() is None

    def state_contains(self, address: str) -> bool:
        """Return True iff ``address`` is a resource currently tracked
        in state. ``address`` is matched as an exact line in
        ``tofu state list`` output (e.g. ``hcloud_server.main``).

        Raises :class:`TofuError` if ``tofu state list`` itself fails —
        callers must not silently treat a failure as "absent", because
        the dangerous interpretation is the inverse: an unreachable
        backend hiding a resource that's about to be destroyed.
        """
        try:
            completed = subprocess.run(
                ["tofu", "state", "list"],
                cwd=self.tofu_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=60.0,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise TofuError(
                f"tofu state list failed in {self.tofu_dir} — cannot "
                f"determine whether {address} is in state",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TofuError(
                f"tofu state list timed out in {self.tofu_dir} — cannot "
                f"determine whether {address} is in state",
            ) from exc
        return address in completed.stdout.splitlines()

    def diagnose_state(self) -> str | None:
        """Return ``None`` when state is initialised + accessible.

        Otherwise returns a short human-readable reason string —
        useful for surfacing in operator-facing error messages
        instead of the generic "state … is not initialised". PR #535
        R2 #2: ``state_list_ok`` returned False for several distinct
        causes (binary missing, backend auth/timeout, state really
        empty), and the pipeline conflated them into one error
        message that was misleading when the real problem was e.g.
        a missing ``tofu`` binary or an R2 backend timeout.

        Possible return values:
        - ``"directory not found: <path>"``
        - ``"tofu binary not found on PATH"``
        - ``"tofu state list timed out after Ns"``
        - ``"state list failed (rc=N): <stderr-tail>"``
        - ``None`` (state OK)
        """
        if not self.tofu_dir.is_dir():
            return f"directory not found: {self.tofu_dir}"
        try:
            completed = subprocess.run(
                ["tofu", "state", "list"],
                cwd=self.tofu_dir,
                check=False,
                capture_output=True,
                text=True,
                timeout=60.0,
            )
        except FileNotFoundError:
            return "tofu binary not found on PATH"
        except subprocess.TimeoutExpired:
            return "tofu state list timed out after 60s"
        if completed.returncode == 0:
            return None
        tail = (completed.stderr or completed.stdout or "").strip()[-300:]
        if tail:
            return f"state list failed (rc={completed.returncode}): {tail}"
        return f"state list failed (rc={completed.returncode})"


@dataclass(frozen=True)
class R2Credentials:
    """Parsed contents of ``tofu/.r2-credentials``.

    The pipeline injects these into ``os.environ`` as
    ``AWS_ACCESS_KEY_ID`` + ``AWS_SECRET_ACCESS_KEY`` BEFORE any tofu
    call (the R2 backend reads them from the env). We model them as a
    typed dataclass instead of a dict so the caller can't accidentally
    pass the wrong shape.
    """

    access_key_id: str
    secret_access_key: str


# Shell-style ``KEY="value"`` or ``KEY=value`` line. Anchored to start-
# of-line so a stray ``=`` inside a comment or value doesn't match.
# Captures KEY (post-validated against expected names) and value (with
# surrounding double-quotes optionally stripped). The regex
# deliberately tolerates whitespace around ``=`` so a hand-edited file
# with ``KEY = value`` still parses.
_R2_CRED_LINE = re.compile(
    r'^\s*(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*"?(?P<value>[^"\n\r]*)"?\s*$',
    re.MULTILINE,
)


def load_r2_credentials(creds_file: Path) -> R2Credentials | None:
    """Parse ``tofu/.r2-credentials`` if it exists.

    The file is a simple shell-source-able assignments list::

        R2_ACCESS_KEY_ID="abc123"
        R2_SECRET_ACCESS_KEY="def456"

    Returns ``None`` when the file doesn't exist (legitimate skip in
    local-dev / CI without R2 backend; pipeline continues with
    whatever AWS_* env the operator already set). Raises
    :class:`TofuError` when the file exists but doesn't contain BOTH
    expected keys (mis-named keys / malformed syntax / one-key-only
    is operator error and a silent skip would mask it leading to a
    "tofu state inaccessible" error 30 seconds later that doesn't
    point at the credential file).
    """
    if not creds_file.is_file():
        return None
    try:
        text = creds_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise TofuError(f"could not read {creds_file}: {type(exc).__name__}: {exc}") from exc

    parsed: dict[str, str] = {}
    for match in _R2_CRED_LINE.finditer(text):
        parsed[match.group("key")] = match.group("value")

    access_key = parsed.get("R2_ACCESS_KEY_ID", "")
    secret_key = parsed.get("R2_SECRET_ACCESS_KEY", "")
    if not access_key or not secret_key:
        raise TofuError(
            f"{creds_file} is missing R2_ACCESS_KEY_ID and/or "
            "R2_SECRET_ACCESS_KEY (file present but malformed)"
        )
    return R2Credentials(
        access_key_id=access_key,
        secret_access_key=secret_key,
    )
