"""Kestra flow-registration client.

Registers the two ``system.git-sync`` / ``system.flow-sync`` flows
that drive the workspace-repo onboarding loop, and optionally
triggers a one-shot ``flow-sync`` execution so user-seeded flows
appear immediately instead of waiting for the 15-min cron.

The architecture uses ``ssh.SSHClient.port_forward`` to open a tunnel
and talk to Kestra's REST API via local ``requests`` calls, surfacing
HTTP errors as typed Python exceptions. No server-side rendered bash,
no heredoc-quoting, and the entire flow logic is unit-testable
against ``responses``-mocked HTTP without ever running ssh.

API:

- :class:`KestraClient` — basic-auth REST client. ``wait_ready``,
  ``register_flow`` (POST 200/201 / 422 → PUT 200/201 / failed),
  ``execute_flow``, ``wait_for_execution``.
- :func:`render_system_flow_yaml` — string-template YAML builder for
  the two system flows.
- :func:`run_register_system_flows` — top-level orchestrator: takes
  an already-forwarded ``base_url``, instantiates KestraClient,
  waits for Kestra, registers both flows, optionally triggers
  ``flow-sync`` and verifies that the canonical seeded flow appears.
  Caller (the CLI in ``__main__._kestra_register_system_flows``) is
  responsible for opening the SSH port-forward — keeping the tunnel
  outside this function lets ``responses``-mock the HTTP layer in
  tests without an ssh roundtrip.

Auth note (R4): basic-auth credentials are passed to ``requests`` via
the ``auth=(user, pass)`` keyword, which puts them in the
``Authorization`` header — never in argv on either host (we don't
shell out at all here, except to ssh for the tunnel which carries
no service-side credentials in argv).
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import Literal

import requests

from nexus_deploy.config import NexusConfig

# Default HTTP timeouts:
# - connect: short (TCP setup) — Kestra is local via tunnel; if it
#   doesn't accept connection in 3s, something is structurally wrong.
# - read: longer (Kestra v1.0 OSS can pause on heavy plugin work
#   especially first-call after restart) — 15s gives the JVM time to
#   warm up the request handler without hanging the deploy.
#
# Polling helpers (``wait_ready``, ``wait_for_execution``) compute a
# per-request override via :func:`_http_timeout_for_deadline` so the
# read timeout can never block past the caller's deadline. Without
# the override, a 0.1s ``timeout_s`` could block ~15s on a single
# stalled probe (TCP accepted, body never arrived) and silently
# violate the timeout contract.
_CONNECT_TIMEOUT_S: float = 3.0
_READ_TIMEOUT_S: float = 15.0
_HTTP_TIMEOUT: tuple[float, float] = (_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S)


def _http_timeout_for_deadline(deadline: float) -> tuple[float, float]:
    """Build a (connect, read) tuple clamped to the time remaining.

    Connect timeout is also clamped to keep ``wait_ready(timeout_s=0.05)``
    honest — a TCP-RST after a stalled SYN could otherwise eat the
    whole 3s connect default. Both legs are floored at 0.1s so the
    ``requests`` library doesn't hit its own zero-timeout edge case.
    """
    remaining = max(deadline - time.monotonic(), 0.1)
    return (
        min(_CONNECT_TIMEOUT_S, remaining),
        min(_READ_TIMEOUT_S, remaining),
    )


RegisterStatus = Literal["created", "updated", "failed"]
# Kestra-side states + two synthetic states the orchestrator emits:
# - TRIGGER_FAILED: execute_flow raised KestraError (couldn't even start).
#   Distinct from FAILED (ran but errored) and from None (caller opted
#   out of triggering); is_success treats it as a failure so the deploy
#   gets a yellow warning rather than a silent green pass.
# - SEED_FLOW_MISSING: execute reached SUCCESS, but the canonical
#   nexus-tutorials.r2-taxi-pipeline flow isn't visible afterwards.
#   Same is_success treatment as TRIGGER_FAILED — operator needs to
#   know the workspace repo wasn't seeded as expected.
ExecutionState = Literal[
    "SUCCESS",
    "FAILED",
    "KILLED",
    "RUNNING",
    "CREATED",
    "UNKNOWN",
    "TRIGGER_FAILED",
    "SEED_FLOW_MISSING",
]

# Canonical seeded flow that system.flow-sync should produce after
# pulling nexus_seeds/kestra/flows/ from the workspace repo. Hardcoded
# because it's the single ship-with-Nexus-Stack tutorial flow under
# the nexus-tutorials namespace, and "did flow-sync actually run?"
# needs a deterministic check, not a guess across all user flows.
_SEED_VERIFICATION_NS = "nexus-tutorials"
_SEED_VERIFICATION_ID = "r2-taxi-pipeline"


@dataclass(frozen=True)
class RegisterResult:
    """Outcome of one ``register_flow`` call.

    ``name`` is the fully-qualified ``<namespace>.<flow_id>`` form
    used in deploy logs. ``detail`` carries the HTTP status the
    operator needs to debug a ``failed`` (e.g. ``"POST 401"``).
    """

    name: str
    status: RegisterStatus
    detail: str = ""


@dataclass(frozen=True)
class SystemFlowsResult:
    """Aggregate of the system-flow registration + onboarding execution."""

    flows: tuple[RegisterResult, ...]
    execution_state: ExecutionState | None = None  # None if not triggered
    # Set when the post-execute flow_exists() probe couldn't run
    # (5xx/transport blip). Doesn't downgrade the SUCCESS state — a
    # transient HTTP error during verify is recoverable on the next
    # deploy and reclassifying it would be punishing operators for
    # network noise. But we still want it surfaced so the operator
    # sees that the verification step itself didn't complete.
    verify_skipped_reason: str | None = None

    @property
    def is_success(self) -> bool:
        """All flows registered/updated AND (if triggered) execution succeeded.

        ``execution_state == None`` is success ONLY when the orchestrator
        was called with ``trigger_onboarding=False`` (caller deliberately
        skipped). When trigger_onboarding=True and execute_flow raised,
        the orchestrator records ``"TRIGGER_FAILED"`` (NOT None), so
        the silent-pass bug from PR #517 round 1 is closed.
        """
        flows_ok = all(f.status != "failed" for f in self.flows)
        if not flows_ok:
            return False
        # Success: didn't trigger (None) OR triggered and execution
        # ended in SUCCESS. Anything else (FAILED/KILLED/RUNNING/UNKNOWN/
        # TRIGGER_FAILED/SEED_FLOW_MISSING) is a partial-failure.
        return self.execution_state is None or self.execution_state == "SUCCESS"


class KestraError(Exception):
    """Transport-level failure (connection refused, timeout, malformed JSON).

    Distinct from a ``failed`` :class:`RegisterResult` — those represent
    a server response we understood but rejected (4xx/5xx after both
    POST and PUT). KestraError is "we never got a meaningful response".
    Carries no response body in its message: response bodies on auth
    failures can include the credentials we just sent.
    """


class KestraClient:
    """Minimal REST client for Kestra OSS v1.0+.

    Basic-auth via ``requests`` — the credentials live in the
    ``Authorization`` header per request, never in argv (no shell-out
    here). Read/write timeouts are bounded so a stuck JVM during
    plugin load can't deadlock the deploy.
    """

    def __init__(self, base_url: str, *, username: str, password: str) -> None:
        if not username or not password:
            raise ValueError("KestraClient requires non-empty username + password")
        self.base_url = base_url.rstrip("/")
        self._auth = (username, password)

    def wait_ready(self, *, timeout_s: float = 60.0, interval_s: float = 3.0) -> bool:
        """Poll ``GET /api/v1/flows`` until basic-auth-accepted.

        Kestra v1.0 OSS has no health endpoint that respects basic-auth
        without listing data; ``/api/v1/flows`` is the canonical probe.
        Accepted status codes:

        - **200** — fully ready, returns flow list
        - **404** — /api/v1/flows endpoint shape changed in some
          v1.0 patches (read path moved under tenant prefix), but
          basic-auth was accepted to evaluate the path
        - **405** — same endpoint may reject GET in some configs;
          again basic-auth was accepted

        These three == "Kestra is ready and our credentials work".
        Anything else (000/401/403/5xx) keeps the loop running until
        timeout. Returns True on first ready, False on timeout.

        Sleep is **clamped to the deadline**: the loop never sleeps
        past ``timeout_s``, so a caller passing ``timeout_s=0.05``
        gets a sub-second response even with the default 3s interval.
        Without the clamp, the loop would call ``requests.get`` once,
        sleep the full ``interval_s``, then check the deadline — making
        short timeouts effectively floor to ``interval_s``.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                resp = requests.get(
                    f"{self.base_url}/api/v1/flows",
                    auth=self._auth,
                    timeout=_http_timeout_for_deadline(deadline),
                )
            except (requests.ConnectionError, requests.Timeout):
                resp = None
            if resp is not None and resp.status_code in (200, 404, 405):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval_s, remaining))
        return False

    def register_flow(
        self,
        yaml_body: str,
        *,
        namespace: str,
        flow_id: str,
    ) -> RegisterResult:
        """Idempotent register: POST first, fall back to PUT on 422.

        Kestra v1.0 OSS does NOT have an upsert verb — POST is
        create-only (returns 422 with ``"Flow id already exists"`` if
        the flow is there) and PUT is update-only (returns 404 if the
        flow doesn't exist). Neither alone covers re-runs, so we
        chain them.
        """
        full_name = f"{namespace}.{flow_id}"
        try:
            post_resp = requests.post(
                f"{self.base_url}/api/v1/flows",
                auth=self._auth,
                headers={"Content-Type": "application/x-yaml"},
                data=yaml_body.encode("utf-8"),
                timeout=_HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            return RegisterResult(
                name=full_name,
                status="failed",
                detail=f"POST transport ({type(exc).__name__})",
            )

        if post_resp.status_code in (200, 201):
            return RegisterResult(
                name=full_name, status="created", detail=f"POST {post_resp.status_code}"
            )
        if post_resp.status_code != 422:
            return RegisterResult(
                name=full_name,
                status="failed",
                detail=f"POST {post_resp.status_code}",
            )

        # POST 422 → exists → PUT to update
        try:
            put_resp = requests.put(
                f"{self.base_url}/api/v1/flows/{namespace}/{flow_id}",
                auth=self._auth,
                headers={"Content-Type": "application/x-yaml"},
                data=yaml_body.encode("utf-8"),
                timeout=_HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            return RegisterResult(
                name=full_name,
                status="failed",
                detail=f"PUT transport ({type(exc).__name__})",
            )

        if put_resp.status_code in (200, 201):
            return RegisterResult(
                name=full_name,
                status="updated",
                detail=f"POST 422 → PUT {put_resp.status_code}",
            )
        return RegisterResult(
            name=full_name,
            status="failed",
            detail=f"POST 422 → PUT {put_resp.status_code}",
        )

    def execute_flow(self, namespace: str, flow_id: str) -> str:
        """Trigger an execution. Returns the execution ID.

        Raises :class:`KestraError` if Kestra doesn't return a parseable
        execution ID — that's a transport-level failure, not the same
        as the execution running and ending in FAILED state (which
        would surface via :meth:`get_execution_state`).
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/executions/{namespace}/{flow_id}",
                auth=self._auth,
                timeout=_HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise KestraError(f"execute_flow transport ({type(exc).__name__})") from exc
        if resp.status_code not in (200, 201):
            raise KestraError(
                f"execute_flow {namespace}.{flow_id} returned HTTP {resp.status_code}",
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise KestraError("execute_flow response was not JSON") from exc
        exec_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(exec_id, str) or not exec_id:
            raise KestraError("execute_flow response missing 'id'")
        return exec_id

    def get_execution_state(
        self,
        exec_id: str,
        *,
        timeout: tuple[float, float] | None = None,
    ) -> ExecutionState:
        """Read the current execution state. Returns ``"UNKNOWN"`` if Kestra
        responded but the JSON shape is unexpected (don't raise — pollers
        keep going if a transient deserialisation glitch happens).

        ``timeout`` overrides the module-default ``_HTTP_TIMEOUT`` —
        :meth:`wait_for_execution` passes a deadline-clamped value so a
        stalled probe can't blow out the caller's overall timeout.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/executions/{exec_id}",
                auth=self._auth,
                timeout=timeout if timeout is not None else _HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise KestraError(f"get_execution_state transport ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise KestraError(f"get_execution_state HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError:
            return "UNKNOWN"
        if not isinstance(payload, dict):
            return "UNKNOWN"
        state_obj = payload.get("state")
        if not isinstance(state_obj, dict):
            return "UNKNOWN"
        current = state_obj.get("current")
        # Kestra-side states we recognise; others (PAUSED, etc.) coalesce to UNKNOWN
        # so the caller's poll-until-terminal logic doesn't loop forever.
        if current in ("SUCCESS", "FAILED", "KILLED", "RUNNING", "CREATED"):
            return current  # type: ignore[no-any-return]
        return "UNKNOWN"

    def flow_exists(self, namespace: str, flow_id: str) -> bool:
        """``GET /api/v1/flows/<ns>/<id>`` — 200 → exists, 404 → not.

        Used post-``system.flow-sync``-execution to confirm the seeded
        flow actually landed (a SUCCESS execution against an empty
        seed tree wouldn't fail the execution but would leave Kestra
        without the user-visible flow). Other status codes (5xx,
        transport) raise :class:`KestraError` so a network blip
        doesn't get conflated with a true "missing flow" condition.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/flows/{namespace}/{flow_id}",
                auth=self._auth,
                timeout=_HTTP_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise KestraError(f"flow_exists transport ({type(exc).__name__})") from exc
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise KestraError(f"flow_exists HTTP {resp.status_code}")

    def wait_for_execution(
        self,
        exec_id: str,
        *,
        timeout_s: float = 60.0,
        interval_s: float = 2.0,
    ) -> ExecutionState:
        """Poll ``get_execution_state`` until terminal or timeout.

        Terminal states: ``SUCCESS``, ``FAILED``, ``KILLED``. Returns
        whichever was reached, or ``"RUNNING"`` if the timeout fired
        before the execution settled (caller maps to a warning, not a
        deploy failure — the execution may finish in the next minute).

        Sleep is clamped to the deadline (same pattern as
        :meth:`wait_ready`) so short ``timeout_s`` values aren't
        floored to ``interval_s``.
        """
        deadline = time.monotonic() + timeout_s
        last: ExecutionState = "CREATED"
        while time.monotonic() < deadline:
            try:
                last = self.get_execution_state(
                    exec_id, timeout=_http_timeout_for_deadline(deadline)
                )
            except KestraError:
                # Transient — coalesce to UNKNOWN and keep polling.
                # wait_for_execution itself NEVER raises: callers prefer
                # a non-terminal "RUNNING"/"UNKNOWN" return at timeout
                # (yellow warning, the cron tick will retry within 15
                # min) over an exception that would short-circuit
                # the rest of the deploy.
                last = "UNKNOWN"
            if last in ("SUCCESS", "FAILED", "KILLED"):
                return last
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval_s, remaining))
        return last


# ---------------------------------------------------------------------------
# System-flow YAML templates with {placeholder} substitutions for
# per-deploy fields. Schema is
# pinned to Kestra v1.0 OSS plugin shape (SyncNamespaceFiles +
# SyncFlows from io.kestra.plugin.git, both of which require
# targetNamespace / namespace fields on v1.0).
# ---------------------------------------------------------------------------

# Pull-direction flows (Forgejo → Kestra) deliberately have NO
# schedule trigger. They run ONCE at spin-up via the onboarding
# kick-offs in ``run_register_system_flows`` and can additionally
# be triggered manually from the Kestra UI. The previous form
# (cron */15) caused two problems:
#
# 1. **Silent overwrite of UI edits.** Every 15 min the SyncFlows
#    task with ``delete: true`` would reconcile Kestra's
#    ``nexus-tutorials`` namespace to whatever's in the Forgejo
#    fork. A student editing a flow in the Kestra UI had a
#    15-min window before their changes vanished — invisible
#    data loss with no error log.
#
# 2. **Ping-pong with flow-export below.** Push-direction
#    (Kestra → Forgejo, ``system.flow-export``) and pull-direction
#    running on similar cadences caused commit churn: every push
#    triggered a pull which re-pushed identical content.
#
# Steady-state source of truth: Kestra UI for student edits,
# Forgejo for upstream/seeded flows. ``flow-export`` (push) keeps
# Forgejo in sync with UI; ``flow-sync`` (pull) re-hydrates Kestra
# from Forgejo ONLY at spin-up so cross-stack restoration works.
GIT_SYNC_FLOW_TEMPLATE = """\
id: git-sync
namespace: system
description: Pull namespace files (SQL/scripts/queries) from internal Forgejo on spin-up. No schedule — UI edits would otherwise be silently reconciled away.
tasks:
  - id: sync
    type: io.kestra.plugin.git.SyncNamespaceFiles
    url: http://forgejo:3000/{repo_owner}/{repo_name}.git
    branch: {branch}
    username: {admin_username}
    password: "{{{{ secret('FORGEJO_TOKEN') }}}}"
    namespace: "{{{{ flow.namespace }}}}"
    gitDirectory: nexus_seeds/kestra/workflows
"""

FLOW_SYNC_FLOW_TEMPLATE = """\
id: flow-sync
namespace: system
description: Pull flow definitions from internal Forgejo on spin-up. Two-task design separates seeded reference flows from the student's own work — seeds at nexus_seeds/kestra/flows/ → nexus-tutorials.*, student work at kestra/flows/ → my-flows.*. Both load with delete:true so Git is canonical at restore-time; namespaces don't collide so the two reconciles don't interfere.
tasks:
  - id: sync-seeds
    type: io.kestra.plugin.git.SyncFlows
    url: http://forgejo:3000/{repo_owner}/{repo_name}.git
    branch: {branch}
    username: {admin_username}
    password: "{{{{ secret('FORGEJO_TOKEN') }}}}"
    gitDirectory: nexus_seeds/kestra/flows
    targetNamespace: nexus-tutorials
    includeChildNamespaces: true
    delete: true
  - id: sync-user
    type: io.kestra.plugin.git.SyncFlows
    url: http://forgejo:3000/{repo_owner}/{repo_name}.git
    branch: {branch}
    username: {admin_username}
    password: "{{{{ secret('FORGEJO_TOKEN') }}}}"
    gitDirectory: kestra/flows
    targetNamespace: my-flows
    includeChildNamespaces: true
    delete: true
"""

# Push direction: Kestra UI → Forgejo fork. Runs every 10 minutes
# so a stack crash loses at most ~10 minutes of student work.
#
# **Scope: ``my-flows.*`` only.** Two namespaces with two
# different meanings under Option C of the bi-directional sync
# design:
#   - ``nexus-tutorials.*``  — seeded reference material. Lives
#     at ``nexus_seeds/kestra/flows/`` in Git. Read-mostly from
#     the student's perspective. NEVER pushed back from Kestra
#     UI (would corrupt the upstream-distributed examples).
#   - ``my-flows.*``         — the student's own work. Lives at
#     ``kestra/flows/`` in Git (no ``nexus_seeds/`` prefix
#     because it's NOT Nexus-Stack-shipped content). Pushed
#     here by this flow every 10 min.
#
# Recommended student workflow: clone-then-edit. Open the seeded
# tutorial flow, save-as with a fresh id under the ``my-flows``
# namespace. The clone gets auto-exported here; the original
# stays untouched in Git as reference material.
#
# Echo-prevention: ``sourceNamespace: my-flows`` excludes both
# ``system.*`` (infrastructure flows including this exporter)
# AND ``nexus-tutorials.*`` (seeded reference material). The
# PushFlows plugin has no exclude-list, so positive-only
# scoping is the ONLY way to prevent the exporter from
# pushing itself or corrupting upstream seeds.
#
# ``delete: false`` because a UI delete shouldn't auto-rewrite
# Git history. To permanently delete a my-flows.* flow,
# the operator commits the deletion directly in the Forgejo fork.
#
# Synthetic commit identity (``Kestra Auto-Export`` /
# ``kestra@nexus-stack.local``) so commits aren't attributed to
# a real user. The Forgejo push log still shows the admin token
# holder as the pusher — acceptable trade-off.
#
# Conflict behaviour: PushFlows fails loud on
# ``REJECTED_NONFASTFORWARD`` (no force-push, no rebase). A
# parallel direct-to-Forgejo commit from the operator would
# cause this — visible in the Kestra execution log, manually
# resolvable.
FLOW_EXPORT_FLOW_TEMPLATE = """\
id: flow-export
namespace: system
description: Push UI-edited flows from the my-flows.* namespace back to the internal Forgejo fork every 10 min. Source-of-truth direction for student work; loses at most ~10 min on stack crash. Seeded tutorial flows in nexus-tutorials.* are NOT pushed (would corrupt upstream reference material) — copy into my-flows.* first to make edits persistent.
tasks:
  - id: export
    type: io.kestra.plugin.git.PushFlows
    url: http://forgejo:3000/{repo_owner}/{repo_name}.git
    branch: {branch}
    username: {admin_username}
    password: "{{{{ secret('FORGEJO_TOKEN') }}}}"
    sourceNamespace: my-flows
    includeChildNamespaces: true
    flows: "**"
    gitDirectory: kestra/flows
    delete: false
    dryRun: false
    commitMessage: "Auto-export from Kestra UI"
    authorName: "Kestra Auto-Export"
    authorEmail: "kestra@nexus-stack.local"
triggers:
  - id: schedule
    type: io.kestra.core.models.triggers.types.Schedule
    cron: "*/10 * * * *"
"""


def render_system_flow_yaml(
    template: str,
    *,
    repo_owner: str,
    repo_name: str,
    branch: str,
    admin_username: str,
) -> str:
    """Substitute placeholders into a system-flow YAML template.

    The double-brace ``{{{{ secret('FORGEJO_TOKEN') }}}}`` in the templates
    becomes a single ``{{ secret('FORGEJO_TOKEN') }}`` after format —
    that's intentional, it's the Kestra Pebble template syntax that
    must reach the registered flow verbatim.
    """
    return template.format(
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch=branch,
        admin_username=admin_username,
    )


def render_system_flows(
    *,
    repo_owner: str,
    repo_name: str,
    branch: str,
    admin_username: str,
) -> dict[str, str]:
    """Return ``{full_name: yaml_body}`` for all three system flows.

    Three flows in the bi-directional sync system:
      - ``system.git-sync`` (pull, namespace files; spin-up only)
      - ``system.flow-sync`` (pull, flows; spin-up only)
      - ``system.flow-export`` (push, flows; every 10 min)
    """
    common = {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "branch": branch,
        "admin_username": admin_username,
    }
    return {
        "system.git-sync": render_system_flow_yaml(GIT_SYNC_FLOW_TEMPLATE, **common),
        "system.flow-sync": render_system_flow_yaml(FLOW_SYNC_FLOW_TEMPLATE, **common),
        "system.flow-export": render_system_flow_yaml(FLOW_EXPORT_FLOW_TEMPLATE, **common),
    }


def register_all_system_flows(
    client: KestraClient,
    flows: dict[str, str],
) -> tuple[RegisterResult, ...]:
    """Register every flow in ``flows``. Order = caller-provided dict order."""
    results: list[RegisterResult] = []
    for full_name, yaml in flows.items():
        ns, _, flow_id = full_name.partition(".")
        results.append(client.register_flow(yaml, namespace=ns, flow_id=flow_id))
    return tuple(results)


def trigger_git_sync_onboarding(
    client: KestraClient,
    *,
    timeout_s: float = 60.0,
) -> ExecutionState:
    """One-shot execute ``system.git-sync`` (namespace files) at spin-up.

    Symmetric to :func:`trigger_flow_sync_onboarding`. Since the
    pull-direction flows lost their schedule trigger, this is the
    ONLY automated path for namespace files (SQL/scripts/queries)
    to reach Kestra from the Forgejo fork. Without it, seeded
    namespace files would only appear if an operator manually
    triggered the flow from the UI.

    Run BEFORE :func:`trigger_flow_sync_onboarding` so any flow
    that references a namespace file finds its dependency in
    place on first execution.
    """
    exec_id = client.execute_flow("system", "git-sync")
    return client.wait_for_execution(exec_id, timeout_s=timeout_s)


def trigger_flow_sync_onboarding(
    client: KestraClient,
    *,
    timeout_s: float = 60.0,
) -> ExecutionState:
    """One-shot execute ``system.flow-sync`` and wait for terminal state.

    Without this, user-seeded flows in ``nexus_seeds/kestra/flows/`` only
    appear after a manual UI trigger (since the schedule was removed
    to prevent silent overwrite of UI edits) — the deploy would print
    "Deployment Complete" with no user flows visible in the Kestra UI,
    causing reasonable "where are my flows?" confusion. The trigger here
    is best-effort: if the execute call or polling fails, the operator
    can still trigger manually from the UI, so we surface the failure
    as a warning, not a deploy abort.

    Raises :class:`KestraError` only on the initial execute_flow call;
    polling failures coalesce to ``"UNKNOWN"`` then ``"RUNNING"`` at
    timeout (callers treat both as warnings).
    """
    exec_id = client.execute_flow("system", "flow-sync")
    return client.wait_for_execution(exec_id, timeout_s=timeout_s)


def run_register_system_flows(
    config: NexusConfig,
    *,
    base_url: str,
    repo_owner: str,
    repo_name: str,
    branch: str,
    admin_email: str,
    trigger_onboarding: bool = True,
    ready_timeout_s: float = 60.0,
    onboarding_timeout_s: float = 60.0,
) -> SystemFlowsResult:
    """End-to-end: instantiate client, wait, register both flows, optionally
    trigger ``system.flow-sync`` execution.

    Caller is responsible for opening the SSH port-forward to Kestra and
    passing the local ``base_url`` (e.g. ``http://localhost:8085``).
    Keeping the tunnel concern outside this function makes the logic
    testable against ``responses``-mocked HTTP without an ssh roundtrip.

    ``ready_timeout_s`` / ``onboarding_timeout_s`` are exposed primarily
    so unit tests can drive the orchestrator to completion in
    sub-second wall-clock; production callers use the defaults.
    """
    client = KestraClient(
        base_url=base_url,
        username=admin_email,
        password=config.kestra_admin_password or "",
    )
    if not client.wait_ready(timeout_s=ready_timeout_s):
        # Kestra never reached basic-auth-accepted state. All three
        # flows would 401; surface a clean partial result so the
        # caller sees rc=1 (yellow warning, continue).
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="failed", detail="kestra not ready"),
                RegisterResult(name="system.flow-sync", status="failed", detail="kestra not ready"),
                RegisterResult(
                    name="system.flow-export", status="failed", detail="kestra not ready"
                ),
            ),
        )

    flows = render_system_flows(
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch=branch,
        admin_username=config.admin_username or "admin",
    )
    register_results = register_all_system_flows(client, flows)

    if not trigger_onboarding:
        return SystemFlowsResult(flows=register_results)

    # Only trigger the onboarding executes when all register calls
    # succeeded — otherwise we'd execute syncs against a stale
    # flow definition.
    if any(r.status == "failed" for r in register_results):
        return SystemFlowsResult(flows=register_results)

    # Trigger git-sync FIRST so namespace files (SQL/scripts) are
    # in place before any flow that might reference them runs.
    # Best-effort: a failure here does NOT block flow-sync below.
    # Namespace files are auxiliary; flows can still register and
    # execute, just might fail at runtime if they reference a
    # not-yet-synced file. Operator sees that via the per-flow
    # Kestra execution log, not here. (contextlib.suppress is the
    # canonical Python form for "intentionally ignore this
    # exception class".)
    with contextlib.suppress(KestraError):
        trigger_git_sync_onboarding(client, timeout_s=onboarding_timeout_s)

    try:
        exec_state: ExecutionState = trigger_flow_sync_onboarding(
            client, timeout_s=onboarding_timeout_s
        )
    except KestraError:
        # Couldn't even start the onboarding execute → record as
        # TRIGGER_FAILED (NOT None). is_success treats this as a
        # partial-failure so the caller routes to the yellow-warning
        # branch instead of green-success — the onboarding genuinely
        # didn't run, and the operator deserves to see that signal.
        return SystemFlowsResult(flows=register_results, execution_state="TRIGGER_FAILED")

    # If the execution itself didn't reach SUCCESS, surface its terminal
    # state directly — no further verification possible against an
    # incomplete sync.
    if exec_state != "SUCCESS":
        return SystemFlowsResult(flows=register_results, execution_state=exec_state)

    # Post-success verification: the canonical seeded flow
    # (nexus-tutorials.r2-taxi-pipeline) must be visible in Kestra.
    # A SUCCESS execution against an empty seed tree (no flows in the
    # workspace repo) wouldn't surface as FAILED — Kestra's SyncFlows
    # runs cleanly with zero files. Without this check the deploy
    # would print green "registered" while operators couldn't find
    # their tutorial flow.
    try:
        seed_visible = client.flow_exists(_SEED_VERIFICATION_NS, _SEED_VERIFICATION_ID)
    except KestraError as exc:
        # Network blip during verification: don't downgrade the SUCCESS
        # execution to a failure (transient HTTP errors are recoverable
        # on the next deploy; reclassifying would punish operators for
        # network noise). But surface the verify-failed signal via
        # ``verify_skipped_reason`` so the CLI emits a stderr warning —
        # operators see WHY the check didn't complete (HTTP 503 vs
        # auth-rejected vs timeout) and can spot-check manually.
        # ``str(exc)`` is safe here: KestraError messages in this module
        # are constructed from fixed format strings + status codes /
        # exception class names — they never include subprocess output
        # or response bodies, per the KestraError docstring.
        return SystemFlowsResult(
            flows=register_results,
            execution_state=exec_state,
            verify_skipped_reason=str(exc),
        )
    if not seed_visible:
        return SystemFlowsResult(flows=register_results, execution_state="SEED_FLOW_MISSING")
    return SystemFlowsResult(flows=register_results, execution_state="SUCCESS")
