"""Workspace-repo coordinate derivation.

Derives REPO_NAME / FORGEJO_REPO_OWNER / FORGEJO_REPO_URL /
WORKSPACE_BRANCH / FORGEJO_GIT_USER / FORGEJO_GIT_PASS / GIT_AUTHOR /
GIT_EMAIL from raw inputs (DOMAIN, ADMIN_USERNAME, FORGEJO_USER_EMAIL,
GH_MIRROR_REPOS, ...).

Three repo-derivation branches:

1. **mirror + user_email** — first GH_MIRROR_REPOS repo gets forked into
   the user's namespace as ``<repo>_<sanitized_user>``. Owner = user.
2. **mirror + no_user_email** — admin gets the mirror as
   ``mirror-readonly-<repo>``. Owner = admin.
3. **no mirror** — admin gets a default repo named
   ``nexus-<domain-dashed>-workspace``. Owner = admin.

In all three cases the GIT_AUTHOR identity defaults to the user when
both ``forgejo_user_email`` AND ``forgejo_user_pass`` are set, otherwise
falls back to admin.

In mirror mode (when ``gh_mirror_token`` is also set), the upstream
repo's default branch is detected via the GitHub API; gracefully falls
back to ``"main"`` on parse / HTTP error. This lets ``targetNamespace``
in Kestra and the workspace seed point at ``master`` / ``develop`` /
etc. when the upstream isn't ``main``.

Public surface:

* :class:`WorkspaceInputs` — frozen input bundle (reads from env vars).
* :class:`WorkspaceCoords` — frozen output bundle (8 derived fields).
* :func:`derive` — pure-logic mapper. ``http_runner`` kwarg is the DI
  seam for tests; production callers leave it None and get the default
  ``requests``-based GitHub API call.

The orchestrator's ``_phase_workspace_coords`` wraps this — that's
where dual-write to ``state`` / ``self.field`` / ``bootstrap_env``
mirrors happens. This module stays pure: input dataclass in, output
dataclass out, no side effects beyond the optional GitHub HTTP call.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import requests

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_TIMEOUT_S = 10.0
DEFAULT_BRANCH = "main"


@dataclass(frozen=True)
class WorkspaceInputs:
    """Inputs to :func:`derive` — raw env-var-shaped bundle.

    All fields are required strings or None. The CLI handler reads
    them off ``os.environ`` and constructs an instance once per
    deploy. Kept frozen so a phase method can't accidentally mutate
    the inputs while computing the output.
    """

    domain: str
    admin_username: str
    admin_email: str
    forgejo_admin_pass: str | None = None
    forgejo_user_email: str | None = None
    forgejo_user_pass: str | None = None
    gh_mirror_repos: str | None = None
    gh_mirror_token: str | None = None


@dataclass(frozen=True)
class WorkspaceCoords:
    """Output of :func:`derive` — the 8 derived workspace fields.

    These feed both:
    1. The pre-bootstrap pipeline (service_env's optional Forgejo
       workspace block append; firewall-sync is independent).
    2. The post-bootstrap pipeline (forgejo-configure / seed /
       kestra-register / woodpecker-oauth / mirror-setup).

    Mutable mirrors live on ``OrchestratorState`` so later phases
    (notably ``_phase_mirror_setup``) can override e.g. ``repo_name``
    with the user's fork. This dataclass itself is frozen — the
    initial derivation is final.
    """

    repo_name: str
    forgejo_repo_owner: str
    forgejo_repo_url: str
    workspace_branch: str
    forgejo_git_user: str
    forgejo_git_pass: str
    git_author: str
    git_email: str


# Type alias: an http_runner takes (token, "<owner>/<repo>") and returns
# the upstream's default_branch. Returning an empty string means
# "couldn't determine — fall back to main". The DI seam lets tests
# inject deterministic responses without hitting api.github.com.
HttpRunner = Callable[[str, str], str]


def _sanitize_username(username: str) -> str:
    """Replace any non-alphanumeric character with ``_``.

    Used when constructing the per-user fork name from a Forgejo
    username that may contain dots / hyphens.
    """
    return re.sub(r"[^a-zA-Z0-9]", "_", username)


def _parse_first_mirror(gh_mirror_repos: str) -> str:
    """Extract the first comma-separated repo URL from
    ``GH_MIRROR_REPOS``, trim surrounding whitespace. Mirror-mode logic
    branches on the FIRST listed repo — additional repos are
    provisioned by mirror-setup but don't influence workspace-coords.
    """
    return gh_mirror_repos.split(",", 1)[0].strip()


def _parse_owner_repo(github_url: str) -> str:
    """Extract ``"<owner>/<repo>"`` from a GitHub URL.

    Strip ``https?://github.com/`` prefix, query-string + fragment +
    trailing slash + ``.git``. For a non-GitHub URL the function
    returns the input unchanged after this strip pass (e.g.
    ``https://gitlab.com/foo/bar`` → as-is). The caller's
    ``re.match("^[^/]+/[^/]+$", ...)`` check is what ultimately
    gates the API call — this function only normalizes, it does
    NOT filter (PR #533 R1 #6 fixed a docstring that previously
    overstated the filtering behaviour).
    """
    stripped = re.sub(r"^https?://github\.com/", "", github_url)
    stripped = re.sub(r"[?#].*$", "", stripped)
    stripped = stripped.rstrip("/")
    if stripped.endswith(".git"):
        stripped = stripped[: -len(".git")]
    return stripped


def _basename(github_url: str) -> str:
    """Extract the bare repo name from a GitHub URL.

    Take the last path segment of a GitHub URL and strip the
    trailing ``.git``. Used to construct ``mirror-readonly-<repo>``
    and ``<repo>_<sanitized_user>``.
    """
    name = github_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name


def _default_http_runner(token: str, owner_repo: str) -> str:
    """Production GH-API runner: GETs ``/repos/<owner_repo>``, returns
    ``default_branch`` field or empty string on any error.

    Network/parse errors silently fall through to "" so the caller
    falls back to ``"main"``. Same defensive contract as the legacy
    bash (curl ``--silent --show-error`` + ``|| true``).

    Token goes in the Authorization header — never in argv. This is
    what made the bash version use ``curl --config tempfile``: in
    Python the equivalent is automatic, since requests.get builds
    the request internally.
    """
    try:
        response = requests.get(
            f"{GITHUB_API_BASE}/repos/{owner_repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=GITHUB_API_TIMEOUT_S,
        )
        if not response.ok:
            return ""
        data = response.json()
        if not isinstance(data, dict):
            return ""
        branch = data.get("default_branch")
        if isinstance(branch, str):
            return branch
        return ""
    except (requests.RequestException, ValueError):
        # ValueError covers JSON decode errors; RequestException covers
        # connection / timeout / HTTP-error edge cases. Either way we
        # silently fall back to the caller's default.
        return ""


def _resolve_default_branch(
    inputs: WorkspaceInputs,
    *,
    http_runner: HttpRunner | None,
) -> str:
    """Try to detect the upstream's default branch. Returns
    ``"main"`` (the fallback) on any condition that says "we can't
    or shouldn't query GitHub":

    - not in mirror mode
    - GH_MIRROR_TOKEN missing (we'd hit the API unauthenticated; per-IP
      rate limit + risk of returning 401/403 instead of branch info)
    - first mirror URL doesn't match ``<owner>/<repo>`` shape
    - HTTP request fails / parses to empty
    """
    if not inputs.gh_mirror_repos or not inputs.gh_mirror_token:
        return DEFAULT_BRANCH
    first_mirror = _parse_first_mirror(inputs.gh_mirror_repos)
    owner_repo = _parse_owner_repo(first_mirror)
    if not owner_repo or not re.match(r"^[^/]+/[^/]+$", owner_repo):
        return DEFAULT_BRANCH
    runner = http_runner if http_runner is not None else _default_http_runner
    detected = runner(inputs.gh_mirror_token, owner_repo)
    if not detected or detected == "null":
        return DEFAULT_BRANCH
    return detected


def _resolve_workspace_username(inputs: WorkspaceInputs) -> str:
    """User-side username derivation, used both in the per-user fork
    name and in the GIT_AUTHOR identity. When ``FORGEJO_USER_EMAIL`` is
    set, the username = local-part of the email (``foo@bar`` → ``foo``).
    Otherwise falls back to ``ADMIN_USERNAME``.
    """
    if inputs.forgejo_user_email:
        return inputs.forgejo_user_email.split("@", 1)[0]
    return inputs.admin_username


def _resolve_repo_coords(
    inputs: WorkspaceInputs,
    *,
    workspace_username: str,
) -> tuple[str, str, str]:
    """Return ``(repo_name, forgejo_repo_owner, forgejo_repo_url)`` for
    the current input combination. Three branches:

    1. mirror + user_email      → fork in user's namespace
    2. mirror + no_user_email   → admin's read-only mirror
    3. no mirror                → admin's default empty repo
    """
    if inputs.gh_mirror_repos and inputs.forgejo_user_email:
        # Branch 1: mirror + user → fork
        first_mirror = _parse_first_mirror(inputs.gh_mirror_repos)
        upstream_repo = _basename(first_mirror)
        sanitized = _sanitize_username(workspace_username)
        repo_name = f"{upstream_repo}_{sanitized}"
        owner = workspace_username
    elif inputs.gh_mirror_repos:
        # Branch 2: mirror + no user → mirror-readonly
        first_mirror = _parse_first_mirror(inputs.gh_mirror_repos)
        upstream_repo = _basename(first_mirror)
        repo_name = f"mirror-readonly-{upstream_repo}"
        owner = inputs.admin_username
    else:
        # Branch 3: no mirror → default workspace name
        repo_name = f"nexus-{inputs.domain.replace('.', '-')}-workspace"
        owner = inputs.admin_username
    repo_url = f"http://forgejo:3000/{owner}/{repo_name}.git"
    return repo_name, owner, repo_url


def _resolve_git_identity(
    inputs: WorkspaceInputs,
    *,
    workspace_username: str,
) -> tuple[str, str, str, str]:
    """Return ``(forgejo_git_user, forgejo_git_pass, git_author, git_email)``.

    User identity wins when BOTH ``forgejo_user_email`` AND
    ``forgejo_user_pass`` are set; otherwise the admin identity. This
    matches the legacy bash gate: ``[ -n "$FORGEJO_USER_EMAIL" ] &&
    [ -n "$FORGEJO_USER_PASS" ]``.

    On the admin-fallback branch, ``forgejo_admin_pass`` may be None —
    the orchestrator's ``_phase_forgejo_configure`` skips with
    ``status='partial'`` in that case (basic-auth would 401), so
    returning an empty string here is fine.
    """
    if inputs.forgejo_user_email and inputs.forgejo_user_pass:
        return (
            workspace_username,
            inputs.forgejo_user_pass,
            workspace_username,
            inputs.forgejo_user_email,
        )
    return (
        inputs.admin_username,
        inputs.forgejo_admin_pass or "",
        inputs.admin_username,
        inputs.admin_email,
    )


def derive(
    inputs: WorkspaceInputs,
    *,
    http_runner: HttpRunner | None = None,
) -> WorkspaceCoords:
    """Derive all 8 workspace-coords fields from the input bundle.

    Pure logic except for the optional GitHub API call inside
    :func:`_resolve_default_branch`. Pass ``http_runner`` for
    deterministic tests; production callers leave it None.

    Order of derivation:

    1. workspace_username = local-part of email or admin
    2. workspace_branch  = upstream default branch (mirror mode) or "main"
    3. (repo_name, owner, url) per the 3-branch rule
    4. (git_user, git_pass, author, email) per the user/admin gate
    """
    workspace_username = _resolve_workspace_username(inputs)
    branch = _resolve_default_branch(inputs, http_runner=http_runner)
    repo_name, repo_owner, repo_url = _resolve_repo_coords(
        inputs,
        workspace_username=workspace_username,
    )
    git_user, git_pass, git_author, git_email = _resolve_git_identity(
        inputs,
        workspace_username=workspace_username,
    )
    return WorkspaceCoords(
        repo_name=repo_name,
        forgejo_repo_owner=repo_owner,
        forgejo_repo_url=repo_url,
        workspace_branch=branch,
        forgejo_git_user=git_user,
        forgejo_git_pass=git_pass,
        git_author=git_author,
        git_email=git_email,
    )
