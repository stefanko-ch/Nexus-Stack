"""Tests for nexus_deploy.workspace_coords.

Pure-logic test surface. Three repo-derivation branches + the
optional GitHub API default-branch detection. The HTTP runner is
injected via the ``http_runner`` DI seam so no test hits api.github.com.

Coverage targets:
- 3 case-fixture snapshots: mirror+user, mirror+no-user, no-mirror
- Default-branch resolution: success, fallback to "main" on ANY error path
- Workspace-username derivation (email local-part vs admin fallback)
- Git-identity selection (user when both email+pass set, else admin)
- _sanitize_username, _parse_first_mirror, _parse_owner_repo, _basename
- HttpRunner DI: assert no live HTTP unless production runner is unmocked
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from nexus_deploy.workspace_coords import (
    DEFAULT_BRANCH,
    WorkspaceCoords,
    WorkspaceInputs,
    _basename,
    _default_http_runner,
    _parse_first_mirror,
    _parse_owner_repo,
    _resolve_default_branch,
    _resolve_git_identity,
    _resolve_repo_coords,
    _resolve_workspace_username,
    _sanitize_username,
    derive,
)

# ---------------------------------------------------------------------------
# Pure-string helpers
# ---------------------------------------------------------------------------


def test_sanitize_username_replaces_non_alphanumeric() -> None:
    assert _sanitize_username("stefan.koch") == "stefan_koch"
    assert _sanitize_username("foo-bar+baz") == "foo_bar_baz"
    assert _sanitize_username("alice123") == "alice123"
    assert _sanitize_username("") == ""


def test_sanitize_username_keeps_unicode_letters_collapsed() -> None:
    """The sanitiser collapses every non-``[a-zA-Z0-9]`` character to
    ``_`` — non-ASCII letters DO get sanitised. Unicode-aware would
    be a behaviour change."""
    assert _sanitize_username("müller") == "m_ller"


def test_parse_first_mirror_strips_whitespace_and_takes_first() -> None:
    assert (
        _parse_first_mirror("  https://github.com/foo/bar.git  ,  https://github.com/baz/qux  ")
        == "https://github.com/foo/bar.git"
    )
    assert _parse_first_mirror("https://github.com/foo/bar") == "https://github.com/foo/bar"


def test_parse_owner_repo_strips_prefix_and_dotgit() -> None:
    assert _parse_owner_repo("https://github.com/owner/repo.git") == "owner/repo"
    assert _parse_owner_repo("http://github.com/owner/repo/") == "owner/repo"
    assert _parse_owner_repo("https://github.com/owner/repo?branch=main") == "owner/repo"
    assert _parse_owner_repo("https://github.com/owner/repo#fragment") == "owner/repo"


def test_parse_owner_repo_returns_input_for_non_github() -> None:
    """Non-github URL passes through unchanged after the prefix-strip
    no-op. The caller's regex check (``^[^/]+/[^/]+$``) is what decides
    whether to query the API."""
    assert _parse_owner_repo("https://gitlab.com/owner/repo") == "https://gitlab.com/owner/repo"


def test_basename_strips_dotgit_and_trailing_slash() -> None:
    assert _basename("https://github.com/owner/repo.git") == "repo"
    assert _basename("https://github.com/owner/repo/") == "repo"
    assert _basename("https://github.com/owner/repo") == "repo"


# ---------------------------------------------------------------------------
# _resolve_workspace_username
# ---------------------------------------------------------------------------


def test_workspace_username_uses_email_local_part_when_set() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_user_email="alice.bob@example.com",
    )
    assert _resolve_workspace_username(inputs) == "alice.bob"


def test_workspace_username_falls_back_to_admin_when_no_user_email() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_user_email=None,
    )
    assert _resolve_workspace_username(inputs) == "admin"


# ---------------------------------------------------------------------------
# _resolve_repo_coords — three branches
# ---------------------------------------------------------------------------


def test_repo_coords_branch1_mirror_plus_user_email_produces_fork() -> None:
    """Branch 1: GH_MIRROR_REPOS + FORGEJO_USER_EMAIL set → fork in user
    namespace as ``<repo>_<sanitized_user>``."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_user_email="alice.bob@example.com",
        gh_mirror_repos="https://github.com/upstream/Bsc_EDS_GIS.git",
    )
    repo_name, owner, url = _resolve_repo_coords(inputs, workspace_username="alice.bob")
    assert repo_name == "Bsc_EDS_GIS_alice_bob"
    assert owner == "alice.bob"
    assert url == "http://forgejo:3000/alice.bob/Bsc_EDS_GIS_alice_bob.git"


def test_repo_coords_branch2_mirror_no_user_email_produces_mirror_readonly() -> None:
    """Branch 2: GH_MIRROR_REPOS set, no user email → admin's
    read-only mirror as ``mirror-readonly-<repo>``."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_user_email=None,
        gh_mirror_repos="https://github.com/upstream/Bsc_EDS_GIS.git",
    )
    repo_name, owner, url = _resolve_repo_coords(inputs, workspace_username="admin")
    assert repo_name == "mirror-readonly-Bsc_EDS_GIS"
    assert owner == "admin"
    assert url == "http://forgejo:3000/admin/mirror-readonly-Bsc_EDS_GIS.git"


def test_repo_coords_branch3_no_mirror_produces_default_workspace() -> None:
    """Branch 3: no mirror → admin's default empty workspace as
    ``nexus-<domain-dashed>-workspace``."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos=None,
    )
    repo_name, owner, url = _resolve_repo_coords(inputs, workspace_username="admin")
    assert repo_name == "nexus-example-com-workspace"
    assert owner == "admin"
    assert url == "http://forgejo:3000/admin/nexus-example-com-workspace.git"


def test_repo_coords_branch3_handles_subdomain_in_domain() -> None:
    """``my.domain.com`` → ``nexus-my-domain-com-workspace`` (every dot
    becomes a dash)."""
    inputs = WorkspaceInputs(
        domain="my.domain.com",
        admin_username="admin",
        admin_email="admin@my.domain.com",
    )
    repo_name, _, _ = _resolve_repo_coords(inputs, workspace_username="admin")
    assert repo_name == "nexus-my-domain-com-workspace"


# ---------------------------------------------------------------------------
# _resolve_git_identity — user vs admin gate
# ---------------------------------------------------------------------------


def test_git_identity_uses_user_when_both_email_and_pass_set() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_user_email="alice@example.com",
        forgejo_user_pass="user-pw",
    )
    git_user, git_pass, git_author, git_email = _resolve_git_identity(
        inputs,
        workspace_username="alice",
    )
    assert git_user == "alice"
    assert git_pass == "user-pw"
    assert git_author == "alice"
    assert git_email == "alice@example.com"


def test_git_identity_falls_back_to_admin_when_user_pass_missing() -> None:
    """Even with email set, missing password forces admin identity —
    matches the canonical layout's ``[ -n "$FORGEJO_USER_EMAIL" ] && [ -n "$FORGEJO_USER_PASS" ]``."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_admin_pass="admin-pw",
        forgejo_user_email="alice@example.com",
        forgejo_user_pass=None,
    )
    git_user, git_pass, git_author, git_email = _resolve_git_identity(
        inputs,
        workspace_username="alice",
    )
    assert git_user == "admin"
    assert git_pass == "admin-pw"
    assert git_author == "admin"
    assert git_email == "admin@example.com"


def test_git_identity_admin_branch_with_no_admin_pass_returns_empty_string() -> None:
    """Admin password may legitimately be unset (orchestrator's
    forgejo-configure phase will skip with status='partial' in that
    case). Function returns empty string — the orchestrator decides."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_admin_pass=None,
    )
    _, git_pass, _, _ = _resolve_git_identity(inputs, workspace_username="admin")
    assert git_pass == ""


# ---------------------------------------------------------------------------
# _resolve_default_branch — early-return paths + happy path
# ---------------------------------------------------------------------------


def test_default_branch_returns_main_when_no_mirror() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos=None,
    )
    assert _resolve_default_branch(inputs, http_runner=_should_not_be_called) == DEFAULT_BRANCH


def test_default_branch_returns_main_when_no_token() -> None:
    """Even with mirror_repos, a missing GH_MIRROR_TOKEN means we don't
    hit GitHub — unauthenticated requests risk per-IP rate limit."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos="https://github.com/o/r.git",
        gh_mirror_token=None,
    )
    assert _resolve_default_branch(inputs, http_runner=_should_not_be_called) == DEFAULT_BRANCH


def test_default_branch_returns_main_when_owner_repo_unparseable() -> None:
    """Non-github URL or malformed shape → fallback. The runner
    should NOT be invoked for an unparseable URL."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos="not-a-url",
        gh_mirror_token="ghp_xxx",
    )
    assert _resolve_default_branch(inputs, http_runner=_should_not_be_called) == DEFAULT_BRANCH


def test_default_branch_calls_runner_and_returns_detected() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos="https://github.com/owner/repo.git",
        gh_mirror_token="ghp_xxx",
    )

    def _runner(token: str, owner_repo: str) -> str:
        assert token == "ghp_xxx"
        assert owner_repo == "owner/repo"
        return "develop"

    assert _resolve_default_branch(inputs, http_runner=_runner) == "develop"


def test_default_branch_falls_back_to_main_when_runner_returns_empty() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos="https://github.com/owner/repo.git",
        gh_mirror_token="ghp_xxx",
    )
    assert _resolve_default_branch(inputs, http_runner=lambda _t, _r: "") == DEFAULT_BRANCH


def test_default_branch_falls_back_to_main_when_runner_returns_null_string() -> None:
    """Defensive: if the GitHub API returned ``"default_branch": null``
    and the runner stringified it, treat as fallback (matches the
    bash ``[ "$DETECTED_BRANCH" != "null" ]`` check)."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        gh_mirror_repos="https://github.com/owner/repo.git",
        gh_mirror_token="ghp_xxx",
    )
    assert _resolve_default_branch(inputs, http_runner=lambda _t, _r: "null") == DEFAULT_BRANCH


def _should_not_be_called(_token: str, _owner_repo: str) -> str:
    raise AssertionError("http_runner should not be called on the early-return paths")


# ---------------------------------------------------------------------------
# _default_http_runner — production GH API runner
# ---------------------------------------------------------------------------


def test_default_http_runner_returns_default_branch_on_200() -> None:
    """Mocks requests.get; verifies token + URL path; returns body's
    default_branch field."""
    response = MagicMock(spec=requests.Response)
    response.ok = True
    response.json.return_value = {"default_branch": "develop"}
    with patch("nexus_deploy.workspace_coords.requests.get", return_value=response) as mock_get:
        result = _default_http_runner("ghp_xxx", "owner/repo")
    assert result == "develop"
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.github.com/repos/owner/repo"
    assert kwargs["headers"]["Authorization"] == "Bearer ghp_xxx"
    assert kwargs["headers"]["Accept"] == "application/vnd.github+json"


def test_default_http_runner_returns_empty_on_non_2xx() -> None:
    """403 / 404 / 500 → empty string (caller falls back to main)."""
    response = MagicMock(spec=requests.Response)
    response.ok = False
    with patch("nexus_deploy.workspace_coords.requests.get", return_value=response):
        assert _default_http_runner("ghp_xxx", "owner/repo") == ""


def test_default_http_runner_returns_empty_on_request_exception() -> None:
    """Connection error / timeout → empty string (graceful)."""
    with patch(
        "nexus_deploy.workspace_coords.requests.get",
        side_effect=requests.ConnectionError("network down"),
    ):
        assert _default_http_runner("ghp_xxx", "owner/repo") == ""


def test_default_http_runner_returns_empty_on_json_decode_error() -> None:
    """Malformed JSON body → empty string."""
    response = MagicMock(spec=requests.Response)
    response.ok = True
    response.json.side_effect = ValueError("not json")
    with patch("nexus_deploy.workspace_coords.requests.get", return_value=response):
        assert _default_http_runner("ghp_xxx", "owner/repo") == ""


def test_default_http_runner_returns_empty_on_non_dict_body() -> None:
    """If GitHub returns a JSON list (defensive: shouldn't happen on
    /repos/{owner}/{repo} but guard in case the API surfaces an array
    of error objects), treat as empty."""
    response = MagicMock(spec=requests.Response)
    response.ok = True
    response.json.return_value = ["error"]
    with patch("nexus_deploy.workspace_coords.requests.get", return_value=response):
        assert _default_http_runner("ghp_xxx", "owner/repo") == ""


def test_default_http_runner_returns_empty_when_default_branch_missing() -> None:
    """200 but no ``default_branch`` field → empty (caller falls back)."""
    response = MagicMock(spec=requests.Response)
    response.ok = True
    response.json.return_value = {"name": "repo"}  # no default_branch
    with patch("nexus_deploy.workspace_coords.requests.get", return_value=response):
        assert _default_http_runner("ghp_xxx", "owner/repo") == ""


# ---------------------------------------------------------------------------
# derive() — end-to-end snapshots for the 3 fixture branches
# ---------------------------------------------------------------------------


def test_derive_no_mirror_no_user_minimal_inputs() -> None:
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_admin_pass="admin-pw",
    )
    coords = derive(inputs)
    assert coords == WorkspaceCoords(
        repo_name="nexus-example-com-workspace",
        forgejo_repo_owner="admin",
        forgejo_repo_url="http://forgejo:3000/admin/nexus-example-com-workspace.git",
        workspace_branch="main",
        forgejo_git_user="admin",
        forgejo_git_pass="admin-pw",
        git_author="admin",
        git_email="admin@example.com",
    )


def test_derive_mirror_no_user_falls_back_to_main_when_no_token() -> None:
    """No GH_MIRROR_TOKEN means we don't query GitHub even though
    mirror is configured — workspace_branch defaults to main."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_admin_pass="admin-pw",
        gh_mirror_repos="https://github.com/upstream/Bsc_EDS_GIS.git",
        gh_mirror_token=None,
    )
    coords = derive(inputs)
    assert coords.repo_name == "mirror-readonly-Bsc_EDS_GIS"
    assert coords.forgejo_repo_owner == "admin"
    assert coords.workspace_branch == "main"


def test_derive_mirror_plus_user_with_default_branch_detection() -> None:
    """Full mirror+user flow with successful default-branch detection."""
    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
        forgejo_admin_pass="admin-pw",
        forgejo_user_email="alice.bob@example.com",
        forgejo_user_pass="user-pw",
        gh_mirror_repos="https://github.com/upstream/Bsc_EDS_GIS.git",
        gh_mirror_token="ghp_xxx",
    )
    coords = derive(inputs, http_runner=lambda _t, _r: "master")
    assert coords == WorkspaceCoords(
        repo_name="Bsc_EDS_GIS_alice_bob",
        forgejo_repo_owner="alice.bob",
        forgejo_repo_url="http://forgejo:3000/alice.bob/Bsc_EDS_GIS_alice_bob.git",
        workspace_branch="master",
        forgejo_git_user="alice.bob",
        forgejo_git_pass="user-pw",
        git_author="alice.bob",
        git_email="alice.bob@example.com",
    )


def test_derive_passes_token_and_owner_repo_to_runner() -> None:
    """Wire-up regression: derive must forward the right token and
    owner_repo to the http_runner."""
    captured: list[tuple[str, str]] = []

    def _runner(token: str, owner_repo: str) -> str:
        captured.append((token, owner_repo))
        return "develop"

    derive(
        WorkspaceInputs(
            domain="example.com",
            admin_username="admin",
            admin_email="admin@example.com",
            gh_mirror_repos="https://github.com/foo/bar.git, https://github.com/baz/qux.git",
            gh_mirror_token="ghp_secret",
        ),
        http_runner=_runner,
    )
    # First mirror only — additional repos in the comma-list don't influence the API call.
    assert captured == [("ghp_secret", "foo/bar")]


def test_derive_no_live_http_when_runner_provided() -> None:
    """Defensive: ensure tests don't accidentally hit api.github.com.
    With an injected runner, requests.get must NOT be called."""
    with patch("nexus_deploy.workspace_coords.requests.get") as mock_get:
        derive(
            WorkspaceInputs(
                domain="example.com",
                admin_username="admin",
                admin_email="admin@example.com",
                gh_mirror_repos="https://github.com/o/r.git",
                gh_mirror_token="ghp_xxx",
            ),
            http_runner=lambda _t, _r: "main",
        )
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# WorkspaceInputs / WorkspaceCoords — frozen contract
# ---------------------------------------------------------------------------


def test_workspace_inputs_frozen() -> None:
    """Inputs must be immutable so a phase method can't accidentally
    mutate them while computing the output."""
    from dataclasses import FrozenInstanceError

    inputs = WorkspaceInputs(
        domain="example.com",
        admin_username="admin",
        admin_email="admin@example.com",
    )
    with pytest.raises(FrozenInstanceError):
        inputs.domain = "other.com"  # type: ignore[misc]


def test_workspace_coords_frozen() -> None:
    from dataclasses import FrozenInstanceError

    coords = WorkspaceCoords(
        repo_name="r",
        forgejo_repo_owner="o",
        forgejo_repo_url="u",
        workspace_branch="main",
        forgejo_git_user="u",
        forgejo_git_pass="p",
        git_author="a",
        git_email="e",
    )
    with pytest.raises(FrozenInstanceError):
        coords.repo_name = "other"  # type: ignore[misc]
