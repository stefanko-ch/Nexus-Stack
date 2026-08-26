"""Tests for nexus_deploy.kestra.

Mocks HTTP via ``responses`` (already a project dep). All paths
exercised: idempotent POST→PUT register, transport-level errors,
execute + poll, the full ``run_register_system_flows`` orchestrator
including the "kestra not ready" early-return.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests
import responses

from nexus_deploy.config import NexusConfig
from nexus_deploy.kestra import (
    FLOW_EXPORT_FLOW_TEMPLATE,
    FLOW_SYNC_FLOW_TEMPLATE,
    GIT_SYNC_FLOW_TEMPLATE,
    KestraClient,
    KestraError,
    RegisterResult,
    SystemFlowsResult,
    register_all_system_flows,
    render_system_flow_yaml,
    render_system_flows,
    run_register_system_flows,
    trigger_flow_sync_onboarding,
)

BASE_URL = "http://localhost:8085"


def _client() -> KestraClient:
    return KestraClient(BASE_URL, username="admin@example.com", password="kp-secret")


def _make_config(**overrides: Any) -> NexusConfig:
    defaults: dict[str, Any] = {
        "admin_username": "admin",
        "kestra_admin_password": "kp-secret",
    }
    defaults.update(overrides)
    return NexusConfig.from_secrets_json(json.dumps(defaults))


# ---------------------------------------------------------------------------
# KestraClient — constructor
# ---------------------------------------------------------------------------


def test_client_rejects_empty_username() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        KestraClient(BASE_URL, username="", password="x")


def test_client_rejects_empty_password() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        KestraClient(BASE_URL, username="admin", password="")


def test_client_strips_trailing_slash_from_base_url() -> None:
    c = KestraClient("http://kestra.local/", username="u", password="p")
    assert c.base_url == "http://kestra.local"


# ---------------------------------------------------------------------------
# wait_ready — accepted status codes (200, 404, 405)
# ---------------------------------------------------------------------------


@responses.activate
def test_wait_ready_returns_true_on_200() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200, json=[])
    assert _client().wait_ready(timeout_s=2.0, interval_s=0.01) is True


@responses.activate
def test_wait_ready_returns_true_on_404() -> None:
    """404 = endpoint moved (v1.0 patch difference) but basic-auth accepted."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=404)
    assert _client().wait_ready(timeout_s=2.0, interval_s=0.01) is True


@responses.activate
def test_wait_ready_returns_true_on_405() -> None:
    """405 = GET rejected on this path, but basic-auth accepted."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=405)
    assert _client().wait_ready(timeout_s=2.0, interval_s=0.01) is True


@responses.activate
def test_wait_ready_loops_then_succeeds() -> None:
    """Two 401s then a 200 → wait_ready returns True after the third probe."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=401)
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=401)
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200, json=[])
    assert _client().wait_ready(timeout_s=5.0, interval_s=0.01) is True


@responses.activate
def test_wait_ready_returns_false_on_timeout() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=401)
    # Very short timeout, single 401 — loop bails out.
    assert _client().wait_ready(timeout_s=0.05, interval_s=0.05) is False


@responses.activate
def test_wait_ready_handles_connection_errors() -> None:
    """ConnectionError doesn't crash the loop — it just keeps polling."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows",
        body=requests.ConnectionError("boom"),
    )
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    assert _client().wait_ready(timeout_s=5.0, interval_s=0.01) is True


# ---------------------------------------------------------------------------
# register_flow — POST/PUT idempotent dance
# ---------------------------------------------------------------------------


@responses.activate
def test_register_flow_post_201_returns_created() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    result = _client().register_flow("id: x\nnamespace: system", namespace="system", flow_id="x")
    assert result == RegisterResult(name="system.x", status="created", detail="POST 201")


@responses.activate
def test_register_flow_post_200_returns_created() -> None:
    """Some Kestra builds return 200 instead of 201 on first-create."""
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=200)
    result = _client().register_flow("y", namespace="system", flow_id="y")
    assert result.status == "created"


@responses.activate
def test_register_flow_post_422_then_put_200_returns_updated() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=422)
    responses.add(responses.PUT, f"{BASE_URL}/api/v1/flows/system/git-sync", status=200)
    result = _client().register_flow("y", namespace="system", flow_id="git-sync")
    assert result.status == "updated"
    assert "POST 422 → PUT 200" in result.detail


@responses.activate
def test_register_flow_post_422_then_put_4xx_returns_failed() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=422)
    responses.add(responses.PUT, f"{BASE_URL}/api/v1/flows/system/git-sync", status=400)
    result = _client().register_flow("y", namespace="system", flow_id="git-sync")
    assert result.status == "failed"
    assert "POST 422 → PUT 400" in result.detail


@responses.activate
def test_register_flow_post_5xx_returns_failed() -> None:
    """5xx on POST → we don't fall through to PUT (PUT 5xx-prone too)."""
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=500)
    result = _client().register_flow("y", namespace="system", flow_id="y")
    assert result.status == "failed"
    assert "POST 500" in result.detail
    # No PUT call should have fired
    assert len(responses.calls) == 1


@responses.activate
def test_register_flow_post_401_returns_failed_without_put() -> None:
    """401 on POST is auth-rejected — PUT would just fail the same way."""
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=401)
    result = _client().register_flow("y", namespace="system", flow_id="y")
    assert result.status == "failed"
    assert "POST 401" in result.detail


@responses.activate
def test_register_flow_post_connection_error_returns_failed() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/flows",
        body=requests.ConnectionError("boom"),
    )
    result = _client().register_flow("y", namespace="system", flow_id="y")
    assert result.status == "failed"
    assert "transport" in result.detail
    # Detail must NOT include the exception message (could leak any
    # response body the wrapper baked in).
    assert "boom" not in result.detail


@responses.activate
def test_register_flow_post_422_then_put_connection_error_returns_failed() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=422)
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/v1/flows/system/y",
        body=requests.Timeout("slow"),
    )
    result = _client().register_flow("y", namespace="system", flow_id="y")
    assert result.status == "failed"
    assert "transport" in result.detail
    assert "slow" not in result.detail


@responses.activate
def test_register_flow_sends_yaml_content_type() -> None:
    """Kestra requires application/x-yaml; JSON body would 400."""
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    _client().register_flow("y", namespace="system", flow_id="y")
    assert responses.calls[0].request.headers["Content-Type"] == "application/x-yaml"


@responses.activate
def test_register_flow_sends_basic_auth_in_header_not_body() -> None:
    """R4 — credentials must travel in the Authorization header,
    NEVER in the request body or query string."""
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    _client().register_flow("flow-body", namespace="system", flow_id="y")
    req = responses.calls[0].request
    auth_header = req.headers.get("Authorization", "")
    assert auth_header.startswith("Basic ")
    # body must NOT contain the password
    body = req.body or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "kp-secret" not in body
    # URL must NOT contain the password (no query-string smuggle)
    assert "kp-secret" not in (req.url or "")


# ---------------------------------------------------------------------------
# execute_flow + get_execution_state + wait_for_execution
# ---------------------------------------------------------------------------


@responses.activate
def test_execute_flow_returns_id_on_201() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "exec-abc-123"},
    )
    assert _client().execute_flow("system", "flow-sync") == "exec-abc-123"


@responses.activate
def test_execute_flow_raises_on_5xx() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=503,
    )
    with pytest.raises(KestraError, match="HTTP 503"):
        _client().execute_flow("system", "flow-sync")


@responses.activate
def test_execute_flow_raises_on_missing_id() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=200,
        json={"not_id": "x"},
    )
    with pytest.raises(KestraError, match="missing 'id'"):
        _client().execute_flow("system", "flow-sync")


@responses.activate
def test_execute_flow_raises_on_non_json() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=200,
        body="not json",
    )
    with pytest.raises(KestraError, match="not JSON"):
        _client().execute_flow("system", "flow-sync")


@responses.activate
def test_execute_flow_raises_on_connection_error() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        body=requests.ConnectionError("boom"),
    )
    with pytest.raises(KestraError, match="transport"):
        _client().execute_flow("system", "flow-sync")


@responses.activate
def test_get_execution_state_success() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    assert _client().get_execution_state("exec-1") == "SUCCESS"


@responses.activate
def test_get_execution_state_unknown_for_unrecognised_state() -> None:
    """Future Kestra state names (PAUSED, etc.) map to UNKNOWN so the
    poller doesn't loop forever."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "PAUSED"}},
    )
    assert _client().get_execution_state("exec-1") == "UNKNOWN"


@responses.activate
def test_get_execution_state_unknown_for_malformed_response() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"foo": "bar"},  # no .state.current
    )
    assert _client().get_execution_state("exec-1") == "UNKNOWN"


@responses.activate
def test_get_execution_state_raises_on_4xx() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=404,
    )
    with pytest.raises(KestraError, match="HTTP 404"):
        _client().get_execution_state("exec-1")


@responses.activate
def test_get_execution_state_raises_on_connection_error() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        body=requests.ConnectionError("boom"),
    )
    with pytest.raises(KestraError, match="transport"):
        _client().get_execution_state("exec-1")


@responses.activate
def test_get_execution_state_unknown_for_non_json_response() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        body="not json at all",
    )
    assert _client().get_execution_state("exec-1") == "UNKNOWN"


@responses.activate
def test_get_execution_state_unknown_for_top_level_list_response() -> None:
    """Defensive: Kestra returns dict-shaped payload; a list is unexpected
    but the poller must not crash on it."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json=[1, 2, 3],
    )
    assert _client().get_execution_state("exec-1") == "UNKNOWN"


@responses.activate
def test_wait_for_execution_returns_terminal_state() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "RUNNING"}},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    assert _client().wait_for_execution("exec-1", timeout_s=5.0, interval_s=0.01) == "SUCCESS"


@responses.activate
def test_wait_for_execution_returns_running_on_timeout() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "RUNNING"}},
    )
    # 0.05s timeout, all responses RUNNING → returns RUNNING (caller treats as warning)
    state = _client().wait_for_execution("exec-1", timeout_s=0.05, interval_s=0.05)
    assert state == "RUNNING"


@responses.activate
def test_wait_for_execution_handles_kestra_error_then_recovers() -> None:
    """Transient KestraError from get_execution_state → poll continues."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=503,  # raises KestraError on first call
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    assert _client().wait_for_execution("exec-1", timeout_s=5.0, interval_s=0.01) == "SUCCESS"


# ---------------------------------------------------------------------------
# render_system_flow_yaml + render_system_flows
# ---------------------------------------------------------------------------


def test_render_git_sync_substitutes_placeholders() -> None:
    yaml_body = render_system_flow_yaml(
        GIT_SYNC_FLOW_TEMPLATE,
        repo_owner="alice",
        repo_name="ws-repo",
        branch="main",
        admin_username="admin",
    )
    assert "url: http://forgejo:3000/alice/ws-repo.git" in yaml_body
    assert "branch: main" in yaml_body
    assert "username: admin" in yaml_body
    # Pebble template must reach Kestra verbatim — single-brace form
    # after Python's str.format processes the double-brace escape.
    assert "{{ secret('FORGEJO_TOKEN') }}" in yaml_body
    assert "gitDirectory: nexus_seeds/kestra/workflows" in yaml_body


def test_render_flow_sync_pins_target_namespace() -> None:
    """v1.0 plugin requires targetNamespace on every SyncFlows
    task. Both tasks (sync-seeds and sync-user) must specify it,
    and they MUST map to DIFFERENT namespaces so the two
    delete:true reconciles don't fight each other:

      - sync-seeds: nexus_seeds/kestra/flows → nexus-tutorials.*
      - sync-user:  kestra/flows             → my-flows.*

    A future regression that collapses both into the same
    namespace would have each reconcile wiping the other's
    flows; both being non-null is the v1.0 plugin requirement."""
    yaml_body = render_system_flow_yaml(
        FLOW_SYNC_FLOW_TEMPLATE,
        repo_owner="bob",
        repo_name="r",
        branch="dev",
        admin_username="admin",
    )
    # Both targetNamespace mappings present.
    assert "targetNamespace: nexus-tutorials" in yaml_body
    assert "targetNamespace: my-flows" in yaml_body
    # Both source paths.
    assert "gitDirectory: nexus_seeds/kestra/flows" in yaml_body
    assert "gitDirectory: kestra/flows" in yaml_body
    # Two task IDs distinguish seeds from user.
    assert "id: sync-seeds" in yaml_body
    assert "id: sync-user" in yaml_body
    # Both reconcile with delete:true (Git canonical at restore time),
    # safe because they target separate namespaces.
    assert yaml_body.count("delete: true") == 2
    assert yaml_body.count("includeChildNamespaces: true") == 2


def test_render_flow_sync_seeds_and_user_paths_in_correct_tasks() -> None:
    """Pin the path-to-namespace pairing so a future copy-paste
    can't accidentally swap them (e.g. user-path → tutorials
    namespace, which would let UI-edited flows leak into the
    seeded reference namespace and clobber upstream examples)."""
    yaml_body = render_system_flow_yaml(
        FLOW_SYNC_FLOW_TEMPLATE,
        repo_owner="o",
        repo_name="r",
        branch="b",
        admin_username="a",
    )
    # Find each task block by id and assert its gitDirectory +
    # targetNamespace are paired correctly.
    seeds_block = yaml_body.split("id: sync-seeds")[1].split("id: sync-user")[0]
    user_block = yaml_body.split("id: sync-user")[1]
    assert "gitDirectory: nexus_seeds/kestra/flows" in seeds_block
    assert "targetNamespace: nexus-tutorials" in seeds_block
    assert "gitDirectory: kestra/flows" in user_block
    assert "targetNamespace: my-flows" in user_block


def test_render_system_flows_returns_all_three() -> None:
    """The bi-directional sync system has three flows: two pull-direction
    (git-sync for namespace files, flow-sync for flows) and one push-
    direction (flow-export). All three must be rendered together so
    the registration loop in run_register_system_flows registers
    all of them in one batch."""
    flows = render_system_flows(
        repo_owner="alice", repo_name="r", branch="main", admin_username="admin"
    )
    assert set(flows.keys()) == {
        "system.git-sync",
        "system.flow-sync",
        "system.flow-export",
    }
    assert "git-sync" in flows["system.git-sync"]
    assert "flow-sync" in flows["system.flow-sync"]
    assert "flow-export" in flows["system.flow-export"]
    # Each carries the correct task type — guards against accidental
    # template copy-paste swaps.
    assert "SyncNamespaceFiles" in flows["system.git-sync"]
    assert "SyncFlows" in flows["system.flow-sync"]
    assert "PushFlows" in flows["system.flow-export"]


def test_pull_direction_flows_have_no_schedule_trigger() -> None:
    """Pull-direction flows (git-sync + flow-sync) MUST NOT have a
    schedule trigger. The previous form (cron */15) caused two bugs:

    1. Silent overwrite of UI edits: SyncFlows with delete=true would
       reconcile away student edits in nexus-tutorials.* every 15 min,
       invisibly.
    2. Ping-pong with flow-export (the push direction): pull+push on
       similar cadences caused commit churn loops.

    These flows now run ONLY at spin-up via the onboarding kick-offs.
    A future maintainer adding a schedule back would regress both
    bugs — this test is the regression gate."""
    flows = render_system_flows(repo_owner="o", repo_name="r", branch="b", admin_username="a")
    assert "triggers:" not in flows["system.git-sync"], (
        "git-sync must have no schedule — pull-direction at spin-up only"
    )
    assert "triggers:" not in flows["system.flow-sync"], (
        "flow-sync must have no schedule — pull-direction at spin-up only"
    )
    # And no cron string smuggled into the tasks section either.
    assert "cron:" not in flows["system.git-sync"]
    assert "cron:" not in flows["system.flow-sync"]


def test_render_flow_export_pins_source_namespace_for_echo_break() -> None:
    """flow-export's ``sourceNamespace`` is the echo-prevention
    invariant under the two-namespace design (Option C):

      - ``system.*`` excluded → exporter doesn't push itself
      - ``nexus-tutorials.*`` excluded → seeded reference flows
        stay untouched in Git (corrupting upstream reference
        material via UI-edits would lose the tutorial baseline)
      - ``my-flows.*`` is the ONLY pushed namespace → student's
        own work, copy-before-edit pattern

    The PushFlows plugin has no exclude-list, so positive-only
    scoping is the only way to enforce all three constraints."""
    yaml_body = render_system_flow_yaml(
        FLOW_EXPORT_FLOW_TEMPLATE,
        repo_owner="carol",
        repo_name="ws",
        branch="main",
        admin_username="admin",
    )
    assert "type: io.kestra.plugin.git.PushFlows" in yaml_body
    assert "sourceNamespace: my-flows" in yaml_body
    # Anti-regression: under no circumstances should the seeded-
    # reference namespace appear as the source namespace — that
    # would corrupt the tutorial baseline by pushing student
    # edits over upstream files.
    assert "sourceNamespace: nexus-tutorials" not in yaml_body
    assert "includeChildNamespaces: true" in yaml_body
    # Target path is the USER path, not the seeds path.
    assert "gitDirectory: kestra/flows" in yaml_body
    assert "gitDirectory: nexus_seeds/kestra/flows" not in yaml_body
    assert "url: http://forgejo:3000/carol/ws.git" in yaml_body
    assert "branch: main" in yaml_body
    assert "username: admin" in yaml_body
    # Pebble secret reference passes through unchanged.
    assert "{{ secret('FORGEJO_TOKEN') }}" in yaml_body


def test_render_flow_export_is_additive_not_destructive() -> None:
    """``delete: false`` because a UI deletion shouldn't auto-rewrite
    Git history. To permanently delete a flow, the operator commits
    the deletion directly in the Forgejo fork. Pinning this prevents
    a future copy-paste from flow-sync (which uses ``delete: true``
    for the reverse direction) from accidentally enabling destructive
    Git rewrites here."""
    yaml_body = render_system_flow_yaml(
        FLOW_EXPORT_FLOW_TEMPLATE,
        repo_owner="o",
        repo_name="r",
        branch="b",
        admin_username="a",
    )
    assert "delete: false" in yaml_body
    assert "delete: true" not in yaml_body
    assert "dryRun: false" in yaml_body


def test_render_flow_export_uses_synthetic_commit_identity() -> None:
    """Commits land with a synthetic author ('Kestra Auto-Export') so
    Git blame doesn't attribute student work to whoever owns the
    push-token (admin). Real students see 'Kestra Auto-Export' as
    the commit author, distinguishing UI-pushed commits from
    operator-direct commits in the fork."""
    yaml_body = render_system_flow_yaml(
        FLOW_EXPORT_FLOW_TEMPLATE,
        repo_owner="o",
        repo_name="r",
        branch="b",
        admin_username="a",
    )
    assert 'authorName: "Kestra Auto-Export"' in yaml_body
    assert 'authorEmail: "kestra@nexus-stack.local"' in yaml_body
    assert 'commitMessage: "Auto-export from Kestra UI"' in yaml_body


def test_render_flow_export_has_10min_schedule() -> None:
    """flow-export runs every 10 min so a stack crash loses at most
    ~10 minutes of student work. Faster (e.g. */5) would multiply
    commits / R2 egress for marginal recovery; slower (e.g. hourly)
    would lose unacceptable amounts of student work. The 10-min
    cadence is the sweet spot — pinning this guards against a
    future 'optimize cron' that breaks the recovery contract."""
    yaml_body = render_system_flow_yaml(
        FLOW_EXPORT_FLOW_TEMPLATE,
        repo_owner="o",
        repo_name="r",
        branch="b",
        admin_username="a",
    )
    assert 'cron: "*/10 * * * *"' in yaml_body


def test_render_system_flows_does_not_double_substitute_secret_pebble() -> None:
    """The Pebble syntax {{ secret('FORGEJO_TOKEN') }} must remain as
    single-braces in the rendered YAML so Kestra's templating engine
    can interpret it. Python str.format escape uses double-braces in
    the template; if a future contributor accidentally drops the
    escape, .format would treat 'secret' as a placeholder and raise
    KeyError. This test pins the contract."""
    flows = render_system_flows(repo_owner="o", repo_name="r", branch="b", admin_username="a")
    for body in flows.values():
        assert "{{ secret('FORGEJO_TOKEN') }}" in body
        # No double-braces should remain (those would be a Python escape
        # leaking into the rendered Kestra YAML).
        assert "{{{{ secret" not in body
        assert "}}}}" not in body


# ---------------------------------------------------------------------------
# register_all_system_flows + trigger_flow_sync_onboarding
# ---------------------------------------------------------------------------


@responses.activate
def test_register_all_system_flows_returns_one_result_per_flow() -> None:
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    flows = render_system_flows(repo_owner="o", repo_name="r", branch="b", admin_username="a")
    results = register_all_system_flows(_client(), flows)
    assert len(results) == 3
    assert {r.name for r in results} == {
        "system.git-sync",
        "system.flow-sync",
        "system.flow-export",
    }
    assert all(r.status == "created" for r in results)


@responses.activate
def test_trigger_flow_sync_onboarding_returns_terminal_state() -> None:
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "exec-1"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    assert trigger_flow_sync_onboarding(_client(), timeout_s=5.0) == "SUCCESS"


# ---------------------------------------------------------------------------
# run_register_system_flows — top-level orchestrator
# ---------------------------------------------------------------------------


@responses.activate
def test_run_register_system_flows_happy_path_with_onboarding() -> None:
    """Wait → register all three → execute git-sync (namespace files) →
    execute flow-sync → poll SUCCESS → seed-flow visible."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    # Three register POSTs (git-sync, flow-sync, flow-export).
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    # git-sync onboarding (fires BEFORE flow-sync so namespace files
    # are in place when flows that reference them run).
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/git-sync",
        status=201,
        json={"id": "exec-git"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-git",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    # flow-sync onboarding.
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "exec-99"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-99",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    # Post-execute verification: seed flow IS visible.
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/nexus-tutorials/r2-taxi-pipeline",
        status=200,
        json={"id": "r2-taxi-pipeline"},
    )

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    assert result.is_success
    assert result.execution_state == "SUCCESS"
    assert all(f.status in ("created", "updated") for f in result.flows)


@responses.activate
def test_run_register_system_flows_kestra_not_ready_returns_failed_results() -> None:
    """wait_ready times out → both flows reported failed with 'kestra not ready' detail."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=401)

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    assert not result.is_success
    assert all(f.status == "failed" for f in result.flows)
    assert all("not ready" in f.detail for f in result.flows)
    assert result.execution_state is None  # no execute attempt


@responses.activate
def test_run_register_system_flows_triggers_git_sync_before_flow_sync() -> None:
    """The git-sync onboarding (namespace files) must fire BEFORE
    the flow-sync onboarding (flows). A flow that references a
    namespace file would otherwise fail on its first execution
    because the file isn't in Kestra's storage yet. Pin the
    ordering via call-history inspection on responses.calls."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/git-sync",
        status=201,
        json={"id": "g"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/g",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "f"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/f",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/nexus-tutorials/r2-taxi-pipeline",
        status=200,
        json={"id": "r2-taxi-pipeline"},
    )

    run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )

    # Find the execute-POSTs in call order and assert git-sync came
    # before flow-sync. ``PreparedRequest.url`` is typed ``str | None``;
    # coalesce to "" so the substring + endswith checks are
    # unambiguously string ops.
    execute_urls: list[str] = []
    for c in responses.calls:
        url = c.request.url or ""
        if "/api/v1/executions/system/" in url and c.request.method == "POST":
            execute_urls.append(url)
    assert execute_urls[0].endswith("/executions/system/git-sync"), (
        f"git-sync must execute first; got {execute_urls}"
    )
    assert execute_urls[1].endswith("/executions/system/flow-sync"), (
        f"flow-sync must execute second; got {execute_urls}"
    )


@responses.activate
def test_run_register_system_flows_git_sync_onboarding_failure_is_non_blocking() -> None:
    """git-sync onboarding is BEST-EFFORT. If the namespace-files sync
    fails, flow-sync (the primary onboarding) MUST still run — the
    operator can manually retrigger git-sync from the UI later.
    Without this guarantee a transient git-sync hiccup would block
    the entire deploy from reaching success."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    # git-sync execute fails with 5xx (transport error → KestraError).
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/git-sync",
        status=503,
    )
    # flow-sync execute succeeds — this is what we want to prove.
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "f"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/f",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/nexus-tutorials/r2-taxi-pipeline",
        status=200,
        json={"id": "r2-taxi-pipeline"},
    )

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    # Deploy still succeeds — flow-sync state is the canonical
    # success signal, not git-sync.
    assert result.is_success
    assert result.execution_state == "SUCCESS"


@responses.activate
def test_run_register_system_flows_skips_onboarding_if_register_failed() -> None:
    """If even ONE register failed, don't trigger flow-sync (would race
    against stale flow definition)."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=500)  # 2nd register fails

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    assert not result.is_success
    assert any(f.status == "failed" for f in result.flows)
    assert result.execution_state is None  # NOT triggered


@responses.activate
def test_run_register_system_flows_trigger_onboarding_false_skips_execute() -> None:
    """Caller can opt out of the post-register flow-sync trigger."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        trigger_onboarding=False,
        ready_timeout_s=2.0,
    )
    assert result.is_success
    assert result.execution_state is None


@responses.activate
def test_run_register_system_flows_onboarding_kestra_error_recorded_as_trigger_failed() -> None:
    """Execute throws KestraError → execution_state=TRIGGER_FAILED (NOT None).

    Round-2 fix: previously this collapsed to None, which made
    is_success return True even though onboarding never ran. Now the
    distinct sentinel makes the caller route to the yellow-warning
    branch (rc=1) instead of silently green.
    """
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=503,
    )

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    assert result.execution_state == "TRIGGER_FAILED"
    # All registers succeeded — the failure is purely the onboarding execute
    assert all(f.status in ("created", "updated") for f in result.flows)
    # is_success must be False so the CLI returns rc=1
    assert result.is_success is False


@responses.activate
def test_run_register_system_flows_seed_flow_missing_after_success() -> None:
    """SUCCESS execution but the canonical seed flow isn't in Kestra → SEED_FLOW_MISSING.

    A SUCCESS execution against an empty seed tree (no flows in the
    workspace repo) would not surface as FAILED. Without the
    post-execute verify, the deploy would falsely print green
    "registered" while operators couldn't find the tutorial flow.
    """
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "exec-99"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-99",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    # Verification call: 404 — flow not registered
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/nexus-tutorials/r2-taxi-pipeline",
        status=404,
    )

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    assert result.execution_state == "SEED_FLOW_MISSING"
    assert result.is_success is False


@responses.activate
def test_run_register_system_flows_seed_flow_visible_after_success() -> None:
    """SUCCESS + seed flow visible (200) → execution_state stays SUCCESS."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "exec-99"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-99",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/nexus-tutorials/r2-taxi-pipeline",
        status=200,
        json={"id": "r2-taxi-pipeline"},
    )

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    assert result.execution_state == "SUCCESS"
    assert result.is_success is True


@responses.activate
def test_run_register_system_flows_seed_verify_transport_error_keeps_success() -> None:
    """Verification HTTP 5xx → don't downgrade a SUCCESS execution, but
    surface the verify-skipped reason so the operator knows the check
    didn't actually run.
    """
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=200)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(responses.POST, f"{BASE_URL}/api/v1/flows", status=201)
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/v1/executions/system/flow-sync",
        status=201,
        json={"id": "exec-99"},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-99",
        status=200,
        json={"state": {"current": "SUCCESS"}},
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/nexus-tutorials/r2-taxi-pipeline",
        status=503,
    )

    result = run_register_system_flows(
        _make_config(),
        base_url=BASE_URL,
        repo_owner="o",
        repo_name="r",
        branch="main",
        admin_email="admin@example.com",
        ready_timeout_s=0.05,
        onboarding_timeout_s=2.0,
    )
    # Stays SUCCESS despite the verification failure
    assert result.execution_state == "SUCCESS"
    assert result.is_success is True
    # NEW (round-2 fix, sharpened in round 3): the operator sees the
    # ACTIONABLE failure detail (HTTP status code), not just the
    # exception class name. Round-2 wrote `type(exc).__name__` which
    # collapsed every kind of failure to bare "KestraError"; round-3
    # uses str(exc) which carries "flow_exists HTTP 503" / "transport
    # (ConnectionError)" / etc.
    assert result.verify_skipped_reason is not None
    assert "503" in result.verify_skipped_reason
    assert "flow_exists" in result.verify_skipped_reason


# ---------------------------------------------------------------------------
# wait_ready / wait_for_execution — sleep clamps to deadline
# ---------------------------------------------------------------------------


@responses.activate
def test_wait_ready_short_timeout_does_not_block_on_long_interval() -> None:
    """Sleep is clamped to deadline — `timeout_s=0.1, interval_s=10` doesn't
    block 10 seconds. Round-2 fix to make the orchestrator's
    ``ready_timeout_s`` parameter actually honour sub-second values."""
    import time as _time

    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows", status=401)
    start = _time.monotonic()
    result = _client().wait_ready(timeout_s=0.1, interval_s=10.0)
    elapsed = _time.monotonic() - start
    assert result is False
    # Should be ≤ ~0.2s; the old behavior would block the full 10s.
    assert elapsed < 1.0, f"wait_ready blocked {elapsed:.2f}s, expected <1s"


@responses.activate
def test_wait_for_execution_short_timeout_does_not_block_on_long_interval() -> None:
    """Same clamp for wait_for_execution."""
    import time as _time

    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/executions/exec-1",
        status=200,
        json={"state": {"current": "RUNNING"}},
    )
    start = _time.monotonic()
    result = _client().wait_for_execution("exec-1", timeout_s=0.1, interval_s=10.0)
    elapsed = _time.monotonic() - start
    assert result == "RUNNING"
    assert elapsed < 1.0, f"wait_for_execution blocked {elapsed:.2f}s, expected <1s"


def test_http_timeout_for_deadline_clamps_both_legs() -> None:
    """Round-3 fix: per-request HTTP timeout (connect, read) is computed
    from the remaining deadline so a stalled probe (TCP accepted, body
    never arrives) can't blow out a sub-second ``timeout_s``.

    Previously a fixed 15s read timeout meant ``wait_ready(timeout_s=0.1)``
    could block ~15s on a single hung probe and silently violate the
    contract.
    """
    import time as _time

    from nexus_deploy.kestra import _CONNECT_TIMEOUT_S, _http_timeout_for_deadline

    # Tight deadline (50ms in the future) → both legs clamped to ~0.05s
    # (or 0.1s floor, whichever is bigger).
    near = _time.monotonic() + 0.05
    connect, read = _http_timeout_for_deadline(near)
    assert connect <= _CONNECT_TIMEOUT_S
    assert read <= 0.5  # well below the 15s default
    # Both legs floored at 0.1s so requests doesn't hit zero-timeout.
    assert connect >= 0.1
    assert read >= 0.1

    # Far-future deadline → defaults preserved (no point clamping
    # below the original).
    far = _time.monotonic() + 1000
    connect, read = _http_timeout_for_deadline(far)
    assert connect == _CONNECT_TIMEOUT_S
    assert read == 15.0  # the module-level _READ_TIMEOUT_S


# ---------------------------------------------------------------------------
# SystemFlowsResult.is_success edge cases
# ---------------------------------------------------------------------------


def test_is_success_true_when_no_execution_triggered() -> None:
    r = SystemFlowsResult(
        flows=(
            RegisterResult(name="a", status="created"),
            RegisterResult(name="b", status="updated"),
        ),
        execution_state=None,
    )
    assert r.is_success is True


def test_is_success_false_on_running_at_timeout() -> None:
    """Onboarding execution never settled — deploy shouldn't claim success."""
    r = SystemFlowsResult(
        flows=(RegisterResult(name="a", status="created"),),
        execution_state="RUNNING",
    )
    assert r.is_success is False


def test_is_success_false_on_register_failure_even_with_success_execution() -> None:
    """Defensive: a register-fail can't be masked by a later SUCCESS execution."""
    r = SystemFlowsResult(
        flows=(
            RegisterResult(name="a", status="failed"),
            RegisterResult(name="b", status="created"),
        ),
        execution_state="SUCCESS",
    )
    assert r.is_success is False


def test_is_success_false_on_trigger_failed() -> None:
    """TRIGGER_FAILED → onboarding never even started → is_success False.

    Round-2 round of #517: previously this collapsed to None and
    silently passed. The dedicated sentinel pins the contract.
    """
    r = SystemFlowsResult(
        flows=(RegisterResult(name="a", status="created"),),
        execution_state="TRIGGER_FAILED",
    )
    assert r.is_success is False


def test_is_success_false_on_seed_flow_missing() -> None:
    """SEED_FLOW_MISSING → SUCCESS execution but no user flow → is_success False."""
    r = SystemFlowsResult(
        flows=(RegisterResult(name="a", status="created"),),
        execution_state="SEED_FLOW_MISSING",
    )
    assert r.is_success is False


# ---------------------------------------------------------------------------
# flow_exists — post-execute seed verification
# ---------------------------------------------------------------------------


@responses.activate
def test_flow_exists_returns_true_on_200() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/system/git-sync",
        status=200,
        json={"id": "git-sync"},
    )
    assert _client().flow_exists("system", "git-sync") is True


@responses.activate
def test_flow_exists_returns_false_on_404() -> None:
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows/nexus-tutorials/missing", status=404)
    assert _client().flow_exists("nexus-tutorials", "missing") is False


@responses.activate
def test_flow_exists_raises_on_5xx() -> None:
    """5xx is neither yes-it-exists nor no-it-doesn't — raise to caller."""
    responses.add(responses.GET, f"{BASE_URL}/api/v1/flows/system/x", status=503)
    with pytest.raises(KestraError, match="HTTP 503"):
        _client().flow_exists("system", "x")


@responses.activate
def test_flow_exists_raises_on_connection_error() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/v1/flows/system/x",
        body=requests.ConnectionError("boom"),
    )
    with pytest.raises(KestraError, match="transport"):
        _client().flow_exists("system", "x")


# ---------------------------------------------------------------------------
# CLI: _kestra_register_system_flows
# ---------------------------------------------------------------------------


def _set_required_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Default env var set for the CLI tests; overrides override."""
    defaults: dict[str, str] = {
        "FORGEJO_REPO_OWNER": "alice",
        "REPO_NAME": "ws-repo",
        "WORKSPACE_BRANCH": "main",
        "ADMIN_EMAIL": "admin@example.com",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)


def test_cli_kestra_unknown_arg_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _kestra_register_system_flows

    rc = _kestra_register_system_flows(["--bogus"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_kestra_missing_required_env_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _kestra_register_system_flows

    monkeypatch.delenv("FORGEJO_REPO_OWNER", raising=False)
    monkeypatch.delenv("REPO_NAME", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    rc = _kestra_register_system_flows([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing required env" in err


def test_cli_kestra_missing_kestra_pass_returns_one_with_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No Kestra password in SECRETS_JSON → log warning, rc=1.

    Round-2 fix: previously rc=0 (mapped to green "registered" banner).
    rc=1 routes the caller to the yellow-warning branch — accurate signal
    that nothing was registered.
    """
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")
    rc = _kestra_register_system_flows([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "KESTRA_PASS missing" in err


def test_cli_kestra_invalid_json_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: "not json {")
    rc = _kestra_register_system_flows([])
    assert rc == 2


def test_cli_kestra_ssh_tunnel_failure_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tunnel setup failure → typed SSHError → rc=2."""
    from nexus_deploy.__main__ import _kestra_register_system_flows
    from nexus_deploy.ssh import SSHError

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    class _BoomSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _BoomSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            raise SSHError("ssh tunnel to local port 8085 did not come up within 10.0s")

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _BoomSSH)
    rc = _kestra_register_system_flows([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ssh tunnel failed" in err
    # SSHError carries safe fixed-format text — its message IS forwarded
    # because ssh.py guarantees no subprocess output is in there.
    assert "did not come up" in err


def test_cli_kestra_unexpected_exception_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Any non-SSH exception class-name only, no str(exc) leak."""
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("secret-do-not-print")

    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", boom)
    # Make SSHClient + port_forward succeed so we reach the run call
    from contextlib import contextmanager

    class _OkSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _OkSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            yield 8085

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _OkSSH)
    rc = _kestra_register_system_flows([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "secret-do-not-print" not in err


def test_cli_kestra_happy_path_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    def fake_run(*_args: Any, **_kwargs: Any) -> SystemFlowsResult:
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="created", detail="POST 201"),
                RegisterResult(
                    name="system.flow-sync", status="updated", detail="POST 422 → PUT 200"
                ),
            ),
            execution_state="SUCCESS",
        )

    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", fake_run)

    from contextlib import contextmanager

    class _OkSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _OkSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            yield 8085

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _OkSSH)
    rc = _kestra_register_system_flows([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "created=1" in captured.out
    assert "updated=1" in captured.out
    assert "execution=SUCCESS" in captured.out
    assert "system.git-sync: created" in captured.err
    assert "system.flow-sync: updated" in captured.err


def test_cli_kestra_partial_failure_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    def fake_run(*_args: Any, **_kwargs: Any) -> SystemFlowsResult:
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="created", detail="POST 201"),
                RegisterResult(name="system.flow-sync", status="failed", detail="POST 500"),
            ),
            execution_state=None,
        )

    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", fake_run)

    from contextlib import contextmanager

    class _OkSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _OkSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            yield 8085

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _OkSSH)
    rc = _kestra_register_system_flows([])
    assert rc == 1
    captured = capsys.readouterr()
    assert "failed=1" in captured.out
    assert "execution=skipped" in captured.out


def test_cli_kestra_emits_actionable_warning_per_execution_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round-2 fix: instead of bare enum (TRIGGER_FAILED), CLI emits
    a human-actionable hint mirroring the caller's per-case warnings."""
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    def fake_run(*_args: Any, **_kwargs: Any) -> SystemFlowsResult:
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="created", detail="POST 201"),
                RegisterResult(name="system.flow-sync", status="created", detail="POST 201"),
            ),
            execution_state="TRIGGER_FAILED",
        )

    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", fake_run)

    from contextlib import contextmanager

    class _OkSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _OkSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            yield 8085

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _OkSSH)
    rc = _kestra_register_system_flows([])
    assert rc == 1
    err = capsys.readouterr().err
    # The bare enum is shown
    assert "TRIGGER_FAILED" in err
    # The actionable hint is also shown — operator sees the remediation
    assert "first sync will run on the next 15-min cron tick" in err


def test_cli_kestra_emits_seed_flow_missing_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SEED_FLOW_MISSING is the most-likely operator-misconfiguration case:
    the workspace repo is missing the seed flow YAML. The hint must
    point them to the file path that needs to be present."""
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    def fake_run(*_args: Any, **_kwargs: Any) -> SystemFlowsResult:
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="created", detail="POST 201"),
                RegisterResult(name="system.flow-sync", status="created", detail="POST 201"),
            ),
            execution_state="SEED_FLOW_MISSING",
        )

    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", fake_run)

    from contextlib import contextmanager

    class _OkSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _OkSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            yield 8085

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _OkSSH)
    rc = _kestra_register_system_flows([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "SEED_FLOW_MISSING" in err
    assert "nexus_seeds/kestra/flows/r2-taxi-pipeline.yaml" in err


def test_cli_kestra_emits_verify_skipped_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the verify step itself failed (5xx during flow_exists), the
    state stays SUCCESS but the operator sees that the check didn't run."""
    from nexus_deploy.__main__ import _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    def fake_run(*_args: Any, **_kwargs: Any) -> SystemFlowsResult:
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="created", detail="POST 201"),
                RegisterResult(name="system.flow-sync", status="created", detail="POST 201"),
            ),
            execution_state="SUCCESS",
            verify_skipped_reason="flow_exists HTTP 503",
        )

    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", fake_run)

    from contextlib import contextmanager

    class _OkSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _OkSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, *_args: Any, **_kwargs: Any) -> Any:
            yield 8085

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _OkSSH)
    rc = _kestra_register_system_flows([])
    # SUCCESS is preserved → rc=0 (transient verify failure isn't a deploy failure)
    assert rc == 0
    err = capsys.readouterr().err
    assert "seed-flow visibility check skipped" in err
    # Round-3 fix: the verify-skipped message carries the actionable
    # detail (HTTP status), not just the bare exception class name.
    assert "HTTP 503" in err


def test_cli_kestra_uses_dynamically_allocated_local_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round-2 fix: local port is kernel-allocated (not hardcoded 8085)
    so leftover tunnels / local services on 8085 don't clash."""
    from nexus_deploy.__main__ import _allocate_free_port, _kestra_register_system_flows

    _set_required_env(monkeypatch)
    monkeypatch.setattr("sys.stdin.read", lambda: '{"kestra_admin_password": "kp"}')

    captured_local_port: list[int] = []

    from contextlib import contextmanager

    class _CapturingSSH:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _CapturingSSH:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        @contextmanager
        def port_forward(self, local_port: int, *_args: Any, **_kwargs: Any) -> Any:
            captured_local_port.append(local_port)
            yield local_port

    def fake_run(*_args: Any, **_kwargs: Any) -> SystemFlowsResult:
        return SystemFlowsResult(
            flows=(
                RegisterResult(name="system.git-sync", status="created", detail="POST 201"),
                RegisterResult(name="system.flow-sync", status="created", detail="POST 201"),
            ),
            execution_state="SUCCESS",
        )

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _CapturingSSH)
    monkeypatch.setattr("nexus_deploy.__main__.run_register_system_flows", fake_run)

    _kestra_register_system_flows([])
    assert len(captured_local_port) == 1
    # NOT 8085 (the production-side Kestra port). Some kernel-chosen
    # ephemeral port instead — typically in the 32768-60999 range on
    # Linux, 49152-65535 on macOS. Just check it's not the hardcoded
    # value, and that _allocate_free_port returns ints.
    assert captured_local_port[0] != 8085
    assert isinstance(captured_local_port[0], int)
    assert captured_local_port[0] > 0

    # Sanity: _allocate_free_port itself returns a usable port
    p = _allocate_free_port()
    assert isinstance(p, int)
    assert 0 < p < 65536
