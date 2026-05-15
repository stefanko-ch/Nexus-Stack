"""Entry point for `python -m nexus_deploy ...` invocations.

Subcommand dispatcher. Subcommands:

- ``run-pipeline`` — the canonical end-to-end deploy entry point
- ``config dump-shell``
- ``infisical bootstrap`` / ``infisical provision-admin``
- ``secret-sync --stack <jupyter|marimo|kestra>``
- ``seed --repo <owner>/<name> [--root PATH] [--prefix nexus_seeds/]``
- ``compose up --enabled <comma-list>``
- ``services configure --enabled <comma-list>``
- ``kestra register-system-flows``
- ``gitea configure`` / ``gitea woodpecker-oauth`` / ``gitea mirror-setup``
- ``stack-sync --enabled <comma-list>``
- ``setup ssh-config`` / ``setup wait-ssh`` / ``setup ensure-jq`` /
  ``setup wetty-ssh-agent``
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import requests

from nexus_deploy import __version__, hello
from nexus_deploy import hetzner_capacity as _hetzner
from nexus_deploy import pipeline as _pipeline
from nexus_deploy import s3_persistence as _s3_persistence
from nexus_deploy import s3_restore as _s3_restore
from nexus_deploy.compose_runner import run_compose_up
from nexus_deploy.config import ConfigError, NexusConfig
from nexus_deploy.gitea import (
    GiteaError,
    run_configure_gitea,
    run_mirror_setup,
    run_woodpecker_oauth_setup,
)
from nexus_deploy.infisical import (
    BootstrapEnv,
    InfisicalClient,
    compute_folders,
    provision_admin,
)
from nexus_deploy.kestra import run_register_system_flows
from nexus_deploy.orchestrator import Orchestrator
from nexus_deploy.r2_tokens import (
    DEFAULT_NEXUS_R2_PREFIX,
    build_inventory,
    cleanup_orphan_tokens,
)
from nexus_deploy.secret_sync import StackTarget, run_sync_for_stack
from nexus_deploy.seeder import _is_safe_repo_path, run_seed_for_repo
from nexus_deploy.service_env import (
    GiteaWorkspaceConfig,
    ServiceEnvError,
    append_gitea_workspace_block,
    render_all_env_files,
)
from nexus_deploy.services import run_admin_setups
from nexus_deploy.setup import (
    SetupError,
    SSHConfigSpec,
    configure_ssh,
    ensure_jq,
    setup_wetty_ssh_agent,
    wait_for_service_token,
    wait_for_ssh,
)
from nexus_deploy.ssh import SSHClient, SSHError
from nexus_deploy.stack_sync import run_stack_sync


def _config_dump_shell(args: list[str]) -> int:
    """`nexus-deploy config dump-shell [--tofu-dir PATH | --stdin]`.

    Two input modes:
    - ``--tofu-dir PATH`` (default ``tofu/stack``): runs ``tofu output
      -json secrets`` inside that directory.
    - ``--stdin``: reads the SECRETS_JSON payload from stdin. Useful
      when the caller has already invoked ``tofu output`` and wants
      to avoid running it twice.

    Writes shell-eval-able ``VAR=value`` lines to stdout. Consumed via
    ``eval "$(... | python -m nexus_deploy config dump-shell --stdin)"``.
    """
    tofu_dir = Path("tofu/stack")
    tofu_dir_explicit = False
    use_stdin = False
    i = 0
    while i < len(args):
        if args[i] == "--tofu-dir":
            if i + 1 >= len(args):
                print("config dump-shell: --tofu-dir requires a PATH", file=sys.stderr)
                return 2
            tofu_dir = Path(args[i + 1])
            tofu_dir_explicit = True
            i += 2
        elif args[i] == "--stdin":
            use_stdin = True
            i += 1
        else:
            print(f"config dump-shell: unknown arg {args[i]!r}", file=sys.stderr)
            return 2
    if use_stdin and tofu_dir_explicit:
        print(
            "config dump-shell: --stdin and --tofu-dir are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    try:
        config = (
            NexusConfig.from_secrets_json(sys.stdin.read())
            if use_stdin
            else NexusConfig.from_tofu_output(tofu_dir)
        )
    except ConfigError as exc:
        print(f"config dump-shell: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(config.dump_shell())
    return 0


def _infisical_bootstrap(args: list[str]) -> int:
    """`nexus-deploy infisical bootstrap`.

    Reads SECRETS_JSON from stdin, reads the additional ``BootstrapEnv``
    fields (DOMAIN, ADMIN_EMAIL, GITEA_*, OM_PRINCIPAL_DOMAIN,
    WOODPECKER_*, SSH_KEY_BASE64) from environment variables,
    plus PROJECT_ID + INFISICAL_TOKEN + INFISICAL_ENV from environment
    variables. Computes the folders, writes payloads, runs the
    server-side curl loop.

    Note on env-var naming: the BootstrapEnv field is
    ``ssh_private_key_base64`` but the env var seen on the caller
    side is ``SSH_KEY_BASE64`` (computed from
    ``SSH_PRIVATE_KEY_CONTENT`` via ``base64 | tr -d '\n'``). The
    asymmetry preserves the original env-passing convention so
    callers don't need to rename their existing env wiring.

    Required env: ``PROJECT_ID``, ``INFISICAL_TOKEN``.
    Optional env: ``INFISICAL_ENV`` (default ``dev``), the BootstrapEnv
    fields above, ``PUSH_DIR`` (default ``/tmp/infisical-push``).

    Exit codes (the three are distinct so callers can decide whether
    to abort):
    - 0: success, all folders pushed
    - 1: bootstrap completed but some folders reported errors
         (warn-and-continue; the operator can fix partial pushes via
         the UI without aborting the rest of the spin-up)
    - 2: hard failure — input validation, transport (rsync/ssh),
         unexpected exception. Caller should abort.
    """
    if args:
        print(f"infisical bootstrap: unexpected arg {args[0]!r}", file=sys.stderr)
        return 2
    project_id = os.environ.get("PROJECT_ID", "").strip()
    token = os.environ.get("INFISICAL_TOKEN", "").strip()
    if not project_id or not token:
        print(
            "infisical bootstrap: PROJECT_ID and INFISICAL_TOKEN env vars required",
            file=sys.stderr,
        )
        return 2
    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"infisical bootstrap: {exc}", file=sys.stderr)
        return 2
    bootstrap_env = BootstrapEnv(
        domain=os.environ.get("DOMAIN") or None,
        admin_email=os.environ.get("ADMIN_EMAIL") or None,
        gitea_user_email=os.environ.get("GITEA_USER_EMAIL") or None,
        gitea_user_username=os.environ.get("GITEA_USER_USERNAME") or None,
        gitea_repo_owner=os.environ.get("GITEA_REPO_OWNER") or None,
        repo_name=os.environ.get("REPO_NAME") or None,
        om_principal_domain=os.environ.get("OM_PRINCIPAL_DOMAIN") or None,
        woodpecker_gitea_client=os.environ.get("WOODPECKER_GITEA_CLIENT") or None,
        woodpecker_gitea_secret=os.environ.get("WOODPECKER_GITEA_SECRET") or None,
        ssh_private_key_base64=os.environ.get("SSH_KEY_BASE64") or None,
    )
    push_dir = Path(os.environ.get("PUSH_DIR") or "/tmp/infisical-push")  # noqa: S108
    client = InfisicalClient(
        project_id=project_id,
        env=os.environ.get("INFISICAL_ENV") or "dev",
        token=token,
        push_dir=push_dir,
    )
    try:
        folders = compute_folders(config, bootstrap_env)
        result = client.bootstrap(folders)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Hard failure: rsync/ssh exited non-zero, hit the timeout, or
        # the binary wasn't on PATH. Caller sees rc=2 and aborts.
        # Avoid printing exc.cmd because TimeoutExpired/CalledProcessError
        # carry the full argv — we don't want the token (if it ever
        # leaked into argv via a future bug) to land in the workflow log.
        print(
            f"infisical bootstrap: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        # Anything else is a programming error in compute_folders/
        # bootstrap (KeyError, ValidationError, AttributeError, …).
        # Python's default exit code for an unhandled exception is 1,
        # which the caller's rc-dispatch treats as "partial push" —
        # exactly what this catch prevents. Force rc=2 so the caller
        # aborts instead of continuing past a broken bootstrap.
        # We print only the exception CLASS name; ``str(exc)`` and
        # ``repr(exc)`` can carry attribute values that might include
        # secret-bearing fields from a NexusConfig or BootstrapEnv
        # pydantic ValidationError.
        # Class name only (no str/repr): exception args may carry
        # secret-bearing fields from a NexusConfig/BootstrapEnv
        # ValidationError. Operators reproducing locally without
        # secret data will see the full traceback there.
        print(
            f"infisical bootstrap: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    print(
        f"infisical bootstrap: built={result.folders_built} pushed={result.pushed} failed={result.failed}",
    )
    return 0 if result.failed == 0 else 1


def _infisical_provision_admin(args: list[str]) -> int:
    """`nexus-deploy infisical provision-admin`.

    Renders + runs a server-side bash script via SSH that:

    1. Waits for Infisical to be ready (60s container + 120s HTTP).
    2. Detects whether Infisical is already initialized.
    3. If yes: loads saved (token, project_id) from
       ``/opt/docker-server/.infisical-{token,project-id}``.
    4. If no: POST ``/api/v1/admin/bootstrap`` (admin user + org) →
       POST ``/api/v2/workspace`` (project) → save creds to disk.

    Required env: ``ADMIN_EMAIL`` + ``INFISICAL_PASS``.

    Stdout (eval-able by callers):
    - ``INFISICAL_TOKEN=<token>``
    - ``PROJECT_ID=<workspace-id>``

    Both lines are always emitted (even on the not-ready / failure
    paths, with empty values) so an ``eval`` doesn't leak stale
    values from a previous run.

    Exit codes:
    - 0: ``loaded-existing`` or ``freshly-bootstrapped`` —
      (token, project_id) populated, downstream push can proceed.
    - 1: ``not-ready`` / ``loaded-existing-missing-creds`` /
      ``already-bootstrapped-no-saved-creds`` /
      ``bootstrap-failed`` / ``project-create-failed`` — soft fail;
      caller warns and continues without pushing secrets.
    - 2: bad args, transport, unexpected error — caller aborts.
    """
    if args:
        print(f"infisical provision-admin: unexpected arg {args[0]!r}", file=sys.stderr)
        return 2

    admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
    admin_password = os.environ.get("INFISICAL_PASS", "").strip()
    if not admin_email or not admin_password:
        print(
            "infisical provision-admin: ADMIN_EMAIL and INFISICAL_PASS env vars required",
            file=sys.stderr,
        )
        return 2

    try:
        result = provision_admin(
            admin_email=admin_email,
            admin_password=admin_password,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"infisical provision-admin: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"infisical provision-admin: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # Always emit the two values (even empty) — callers eval the
    # assignment to clear any stale value left over from prior runs.
    # shlex.quote handles the empty-string + edge cases.
    import shlex as _shlex

    sys.stdout.write(f"INFISICAL_TOKEN={_shlex.quote(result.token or '')}\n")
    sys.stdout.write(f"PROJECT_ID={_shlex.quote(result.project_id or '')}\n")

    # Per-status stderr line so the workflow log carries the human-
    # readable outcome (the eval-able stdout is for shell consumption).
    sys.stderr.write(f"infisical provision-admin: status={result.status}\n")

    # rc=0 ONLY when the provision actually produced usable credentials
    # (token AND project_id both populated). A `loaded-existing` /
    # `freshly-bootstrapped` status with a dropped token (e.g.
    # malformed-base64 → parse_provision_result returned None for
    # token) MUST be reported as soft-fail so the caller doesn't
    # print "✓ Infisical provisioned" while emitting empty
    # INFISICAL_TOKEN= / PROJECT_ID= lines that downstream eval'd
    # consumers would treat as legitimate. Caught in #530 R2.
    if result.status in ("loaded-existing", "freshly-bootstrapped") and result.has_credentials:
        return 0
    return 1


_VALID_STACKS = ("jupyter", "marimo", "kestra")


def _secret_sync(args: list[str]) -> int:
    """`nexus-deploy secret-sync --stack <jupyter|marimo>`.

    Fetches Infisical secrets, filters/escapes them, and writes the
    result to ``/opt/docker-server/stacks/<stack>/.infisical.env`` on
    the server. On change, restarts the stack via ``docker compose
    up -d <stack>``. One :class:`StackTarget` parametrises each stack's
    output format (jupyter/marimo write plain dotenv lines; kestra
    writes ``SECRET_<KEY>=<base64>`` lines into ``.env`` directly).

    Required env: ``PROJECT_ID``, ``INFISICAL_TOKEN``.
    Optional env: ``INFISICAL_ENV`` (default ``dev``), ``GITEA_TOKEN``
    (special-case append — auto-generated post-Gitea-bootstrap, not
    in Infisical at sync time).

    Exit codes:
    - 0: success, OR sync correctly chose not to write (one of the
         two outage gates fired — operator sees a stderr warning,
         existing file untouched), OR the remote script produced no
         parseable RESULT line (treated as a soft no-op; the inner
         script's own stderr is already in the workflow log for
         diagnosis)
    - 1: partial — file written but at least one folder fetch failed
         (warn-and-continue; the operator can fix the offending
         folder via the Infisical UI without aborting)
    - 2: hard failure — invalid `--stack`, missing required env,
         transport (ssh) failure, unexpected exception. Caller
         should abort.
    """
    stack: str | None = None
    i = 0
    while i < len(args):
        if args[i] == "--stack":
            if i + 1 >= len(args):
                print("secret-sync: --stack requires a value", file=sys.stderr)
                return 2
            stack = args[i + 1]
            i += 2
        else:
            print(f"secret-sync: unknown arg {args[i]!r}", file=sys.stderr)
            return 2
    if stack is None:
        print("secret-sync: --stack <jupyter|marimo> is required", file=sys.stderr)
        return 2
    if stack not in _VALID_STACKS:
        print(
            f"secret-sync: unknown stack {stack!r} (expected one of {_VALID_STACKS})",
            file=sys.stderr,
        )
        return 2

    project_id = os.environ.get("PROJECT_ID", "").strip()
    token = os.environ.get("INFISICAL_TOKEN", "").strip()
    if not project_id or not token:
        print(
            "secret-sync: PROJECT_ID and INFISICAL_TOKEN env vars required",
            file=sys.stderr,
        )
        return 2
    infisical_env = os.environ.get("INFISICAL_ENV") or "dev"
    gitea_token = os.environ.get("GITEA_TOKEN") or ""

    # Kestra writes SECRET_<KEY>=<base64> to .env directly (no separate
    # .infisical.env), and force-recreates so EnvVarSecretProvider
    # loads the new values. Jupyter/Marimo use the original
    # plaintext-to-.infisical.env shape with `up -d` (no force).
    if stack == "kestra":
        target = StackTarget(
            name="kestra",
            key_prefix="SECRET_",
            use_base64_values=True,
            env_file_basename=".env",
            legacy_env_file_basename=None,
            force_recreate=True,
        )
    else:
        target = StackTarget(name=stack)
    try:
        result = run_sync_for_stack(
            target,
            project_id=project_id,
            infisical_token=token,
            infisical_env=infisical_env,
            gitea_token=gitea_token,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Same defence-in-depth as `infisical bootstrap`: never print
        # exc.cmd (carries argv that COULD include secrets if a future
        # bug regressed _remote.ssh_run_script's stdin contract).
        print(
            f"secret-sync: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        # Programming errors (KeyError, AttributeError, etc.) — Python's
        # default rc=1 would collide with the partial-failure semantic,
        # so force rc=2. Class name only — no str/repr, which could
        # embed secret-bearing values.
        print(
            f"secret-sync: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # All-zero counters with wrote=False: either the remote script
    # printed no parseable RESULT line, OR it took the legitimate
    # jq-missing path (which intentionally emits an all-zero RESULT).
    # Both are warn-and-continue (rc=0); the inner script already
    # printed its own warning to stderr (workflow log).
    # Distinguishing them would require a dedicated sentinel; not
    # worth the wire-format churn given both demand the same response.
    if (
        result.pushed == 0
        and result.failed_folders == 0
        and result.succeeded_folders == 0
        and not result.wrote
    ):
        print(
            f"secret-sync: {stack} produced no usable result (see prior warnings)",
        )
        return 0

    if result.wrote and result.failed_folders == 0 and result.collisions == 0:
        print(
            f"secret-sync: {stack} wrote {result.pushed} env-vars (plaintext, exact key names)",
        )
        return 0
    if result.wrote and result.failed_folders > 0:
        print(
            f"secret-sync: {stack} wrote {result.pushed} env-vars "
            f"({result.failed_folders} folder fetch(es) failed — secret set is incomplete)",
        )
        return 1
    if result.wrote and result.collisions > 0:
        print(
            f"secret-sync: {stack} wrote {result.pushed} env-vars "
            f"({result.collisions} cross-folder collision(s) — first-wins applied)",
        )
        return 0
    # wrote=False with non-zero counters — one of the two outage gates
    # fired (succeeded==0 or pushed==0). Existing file untouched.
    # Operator already saw the cause from the inner script's stderr.
    print(
        f"secret-sync: {stack} skipped .infisical.env update (kept previous; see prior warning)",
    )
    return 0


def _seed(args: list[str]) -> int:
    """`nexus-deploy seed --repo <owner>/<name> [--root PATH] [--prefix STR]`.

    Walks the local seed tree (default ``examples/workspace-seeds/``),
    base64-encodes each file, rsyncs the JSON payloads to the server,
    and POSTs each one to Gitea's Contents API under the prefix
    (default ``nexus_seeds/``). Two call-sites use this: non-mirror
    mode (admin-owned repo) and mirror+user mode (user's fork). Each
    invokes this CLI with the appropriate ``--repo`` arg.

    Required env: ``GITEA_TOKEN``.

    Exit codes:
    - 0: all seeds either created (HTTP 201/200) or correctly skipped
         (HTTP 422 = file already exists, user edits persist — #501
         contract).
    - 1: partial — some files failed but at least one succeeded.
         Yellow warning, continue.
    - 2: hard failure — bad ``--repo`` format, missing token, transport
         (ssh/rsync) failure, no parseable RESULT line, unexpected
         exception. Caller should abort.
    """
    repo: str | None = None
    root_arg: str | None = None
    prefix = "nexus_seeds/"
    i = 0
    while i < len(args):
        if args[i] == "--repo":
            if i + 1 >= len(args):
                print("seed: --repo requires a value", file=sys.stderr)
                return 2
            repo = args[i + 1]
            i += 2
        elif args[i] == "--root":
            if i + 1 >= len(args):
                print("seed: --root requires a value", file=sys.stderr)
                return 2
            root_arg = args[i + 1]
            i += 2
        elif args[i] == "--prefix":
            if i + 1 >= len(args):
                print("seed: --prefix requires a value", file=sys.stderr)
                return 2
            prefix = args[i + 1]
            i += 2
        else:
            print(f"seed: unknown arg {args[i]!r}", file=sys.stderr)
            return 2

    if repo is None or "/" not in repo:
        print(
            "seed: --repo <owner>/<name> is required (must contain '/')",
            file=sys.stderr,
        )
        return 2
    repo_owner, _, repo_name = repo.partition("/")
    if not repo_owner or not repo_name:
        print(
            f"seed: invalid --repo {repo!r} — both owner and name required",
            file=sys.stderr,
        )
        return 2

    # Validate --prefix: must be empty (seed into repo root) OR a
    # safe relative directory ending with `/`. The safe-char regex
    # alone is not enough because it permits ``..``, leading ``/``,
    # and empty segments (``//``) — all of which produce dangerous
    # repo_paths when concatenated with the relative file path:
    #   ``../`` + ``kestra/x.yaml`` → ``../kestra/x.yaml``  (escape)
    #   ``/foo/`` + ``kestra/x.yaml`` → ``/foo/kestra/x.yaml`` (absolute)
    #   ``a//b/`` + ``...``           → ``a//b/...`` (empty segment)
    # Surfacing this at CLI parse time saves a wasted spin-up roundtrip.
    if prefix:
        prefix_segments = prefix.split("/")
        # Trailing "/" → last segment is empty; that's the required form.
        # We slice it off before per-segment validation.
        if prefix_segments[-1] != "":
            print(
                f"seed: invalid --prefix {prefix!r} — must end with '/'",
                file=sys.stderr,
            )
            return 2
        body_segments = prefix_segments[:-1]
        if not body_segments or any(
            seg in ("", ".", "..") or not _is_safe_repo_path(seg) for seg in body_segments
        ):
            print(
                f"seed: invalid --prefix {prefix!r} — must be empty or a "
                "safe relative path ending with '/' (no '..', no leading "
                "'/', no empty segments, only [A-Za-z0-9._-] per segment)",
                file=sys.stderr,
            )
            return 2

    token = os.environ.get("GITEA_TOKEN", "").strip()
    if not token:
        print("seed: GITEA_TOKEN env var required", file=sys.stderr)
        return 2

    root = Path(root_arg) if root_arg else Path("examples/workspace-seeds")
    if not root.is_dir():
        print(
            f"seed: root {root!s} is not a directory (skipping with rc=0)",
            file=sys.stderr,
        )
        # Missing seed dir is non-fatal — a deployment without
        # bundled examples is a valid configuration.
        return 0

    try:
        result = run_seed_for_repo(
            repo_owner=repo_owner,
            repo_name=repo_name,
            root=root,
            token=token,
            prefix=prefix,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Same defence-in-depth as `secret-sync`: never print exc.cmd /
        # str(exc) / repr(exc) — they may carry the token.
        print(f"seed: transport failure ({type(exc).__name__})", file=sys.stderr)
        return 2
    except Exception as exc:
        # Force rc=2 (Python's default rc=1 collides with our
        # partial-failure semantic).
        print(f"seed: unexpected error ({type(exc).__name__})", file=sys.stderr)
        return 2

    print(
        f"seed: {repo_owner}/{repo_name} — created={result.created} "
        f"skipped={result.skipped} failed={result.failed}"
    )
    if result.failed > 0:
        if result.created + result.skipped == 0:
            return 2
        return 1
    return 0


def _compose_up(args: list[str]) -> int:
    """`nexus-deploy compose up --enabled <comma-list>`.

    Renders the parallel ``docker compose up -d --build`` loop for
    every enabled service, runs it server-side via ssh, parses the
    RESULT line. Per-service admin-setup hooks (Wikijs, Dify, etc.)
    live in :mod:`nexus_deploy.services`.

    The comma-list is the same ``ENABLED_SERVICES`` set the rest of
    the pipeline consumes; callers pass it as-is. Virtual-service
    expansion + parent-stack deduplication + deferred-services
    skipping happen inside the compose_runner module.

    Exit codes:
    - 0: all enabled services started + verified running.
    - 1: at least one service failed but at least one succeeded
         (caller continues — the operator sees the per-service
         ✗ line for diagnosis).
    - 2: hard failure — invalid args, transport (ssh) failure, no
         parseable RESULT line. Caller should abort.
    """
    if not args or args[0] != "up":
        print("compose: only 'up' subcommand is supported", file=sys.stderr)
        return 2

    enabled_str: str | None = None
    i = 1
    while i < len(args):
        if args[i] == "--enabled":
            if i + 1 >= len(args):
                print("compose up: --enabled requires a value", file=sys.stderr)
                return 2
            enabled_str = args[i + 1]
            i += 2
        else:
            print(f"compose up: unknown arg {args[i]!r}", file=sys.stderr)
            return 2

    if enabled_str is None:
        print(
            "compose up: --enabled <comma-separated-services> is required",
            file=sys.stderr,
        )
        return 2

    enabled = [s.strip() for s in enabled_str.split(",") if s.strip()]
    if not enabled:
        # Empty list = nothing to do = success.
        print("compose up: no services enabled, nothing to do")
        return 0

    try:
        result = run_compose_up(enabled)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"compose up: transport failure ({type(exc).__name__})", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"compose up: unexpected error ({type(exc).__name__})", file=sys.stderr)
        return 2

    print(f"compose up: started={result.started} failed={result.failed}")
    if result.failed > 0:
        if result.started == 0:
            return 2
        return 1
    return 0


def _services_configure(args: list[str]) -> int:
    """`nexus-deploy services configure --enabled <comma-list>`.

    Renders + executes the per-service admin-setup hooks for the
    enabled services that have a renderer in
    ``nexus_deploy.services._HOOK_REGISTRY``. Reads NexusConfig from
    stdin (SECRETS_JSON) and reads BootstrapEnv fields (DOMAIN,
    ADMIN_EMAIL, etc.) from environment variables — same handoff
    pattern as ``infisical bootstrap``.

    Currently shipped: Portainer, n8n, Metabase, LakeFS, OpenMetadata,
    RedPanda, Superset, Filestash (python-side JSON mutation).
    Additional hooks land here as new services need configuration.

    Exit codes:
    - 0: all enabled+supported hooks ended in configured /
         already-configured / skipped-not-ready states (no failures).
    - 1: at least one hook reported status=failed but at least one
         succeeded. Yellow warning, continue.
    - 2: bad args, transport (ssh) failure, or unexpected exception.
         Caller should abort.
    """
    if not args or args[0] != "configure":
        print("services: only 'configure' subcommand is supported", file=sys.stderr)
        return 2

    enabled_str: str | None = None
    i = 1
    while i < len(args):
        if args[i] == "--enabled":
            if i + 1 >= len(args):
                print(
                    "services configure: --enabled requires a value",
                    file=sys.stderr,
                )
                return 2
            enabled_str = args[i + 1]
            i += 2
        else:
            print(f"services configure: unknown arg {args[i]!r}", file=sys.stderr)
            return 2

    if enabled_str is None:
        print(
            "services configure: --enabled <comma-separated-services> is required",
            file=sys.stderr,
        )
        return 2

    enabled = [s.strip() for s in enabled_str.split(",") if s.strip()]
    if not enabled:
        print("services configure: no services enabled, nothing to do")
        return 0

    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"services configure: {exc}", file=sys.stderr)
        return 2
    bootstrap_env = BootstrapEnv(
        domain=os.environ.get("DOMAIN") or None,
        admin_email=os.environ.get("ADMIN_EMAIL") or None,
        gitea_user_email=os.environ.get("GITEA_USER_EMAIL") or None,
        gitea_user_username=os.environ.get("GITEA_USER_USERNAME") or None,
        gitea_repo_owner=os.environ.get("GITEA_REPO_OWNER") or None,
        repo_name=os.environ.get("REPO_NAME") or None,
        om_principal_domain=os.environ.get("OM_PRINCIPAL_DOMAIN") or None,
        woodpecker_gitea_client=os.environ.get("WOODPECKER_GITEA_CLIENT") or None,
        woodpecker_gitea_secret=os.environ.get("WOODPECKER_GITEA_SECRET") or None,
        ssh_private_key_base64=os.environ.get("SSH_KEY_BASE64") or None,
    )

    try:
        result = run_admin_setups(config, bootstrap_env, enabled)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"services configure: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"services configure: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    print(
        f"services configure: configured={result.configured} "
        f"already-configured={result.already_configured} "
        f"skipped-not-ready={result.skipped_not_ready} "
        f"failed={result.failed}"
    )
    if result.failed > 0:
        if result.configured + result.already_configured == 0:
            return 2
        return 1
    return 0


def _kestra_register_system_flows(args: list[str]) -> int:
    """`nexus-deploy kestra register-system-flows`.

    Opens an SSH port-forward to the nexus host. The Kestra container
    listens on port 8080 internally; ``stacks/kestra/docker-compose.yml``
    publishes it as ``8085:8080`` (no explicit host-IP, so it binds
    every interface on the host — but the host firewall blocks external
    8085, so the only reachable path is through ssh + the server's
    loopback). We ``ssh -L 127.0.0.1:<local>:localhost:8085`` to reach
    the host-published port through the tunnel. Once it's up we
    register ``system.git-sync`` + ``system.flow-sync`` via local HTTP
    and trigger a one-shot ``flow-sync`` execution to onboard
    user-seeded flows immediately.

    Reads ``NexusConfig`` from stdin (SECRETS_JSON) and the per-deploy
    repo coordinates from environment variables — same handoff pattern
    as ``services configure``:

    - ``ADMIN_EMAIL`` — Kestra basic-auth username
    - ``GITEA_REPO_OWNER`` — owner of the workspace repo (admin in
      non-mirror, the user in mirror+user mode)
    - ``REPO_NAME`` — workspace repo name
    - ``WORKSPACE_BRANCH`` — git branch (default ``main``)
    - ``KESTRA_HOST`` — SSH host alias (default ``nexus``); exposed
      so a future test deploy can target a different alias

    Exit codes:
    - 0: both flows registered (or already-up-to-date) AND the
         onboarding execute settled in SUCCESS within timeout.
    - 1: at least one flow registration / execution did NOT succeed
         (yellow warning, continue — the cron tick will catch user
         flows later).
    - 2: bad args, ssh tunnel setup failure, or unexpected exception
         (caller should abort).
    """
    if args:
        print(f"kestra register-system-flows: unknown args {args!r}", file=sys.stderr)
        return 2

    repo_owner = os.environ.get("GITEA_REPO_OWNER") or ""
    repo_name = os.environ.get("REPO_NAME") or ""
    branch = os.environ.get("WORKSPACE_BRANCH") or "main"
    admin_email = os.environ.get("ADMIN_EMAIL") or ""
    ssh_host = os.environ.get("KESTRA_HOST") or "nexus"

    missing = [
        name
        for name, val in (
            ("GITEA_REPO_OWNER", repo_owner),
            ("REPO_NAME", repo_name),
            ("ADMIN_EMAIL", admin_email),
        )
        if not val
    ]
    if missing:
        print(
            f"kestra register-system-flows: missing required env: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"kestra register-system-flows: {exc}", file=sys.stderr)
        return 2

    if not config.kestra_admin_password:
        # Round-2 fix: rc=1 routes to the yellow-warning branch —
        # accurate signal that nothing was registered. (Previously
        # rc=0 mis-read as a successful registration.)
        print(
            "kestra register-system-flows: KESTRA_PASS missing from SECRETS_JSON — "
            "skipping (Kestra basic-auth would 401 on every call)",
            file=sys.stderr,
        )
        return 1

    # Round-2 fix: pick a free local port via socket.bind(0) instead of
    # hardcoded 8085. Hardcoded would clash with leftover ssh tunnels
    # or any local service already on 8085; the new pre-bind probe
    # asks the kernel for a free ephemeral port. Tiny race window
    # (the port is closed before ssh -L re-binds) but vastly better
    # than the previous unconditional collision.
    local_port = _allocate_free_port()

    try:
        with (
            SSHClient(ssh_host) as ssh,
            ssh.port_forward(local_port, "localhost", 8085) as port,
        ):
            result = run_register_system_flows(
                config,
                base_url=f"http://localhost:{port}",
                repo_owner=repo_owner,
                repo_name=repo_name,
                branch=branch,
                admin_email=admin_email,
            )
    except SSHError as exc:
        # SSHError is the typed transport-failure path from ssh.py.
        # str(exc) is intentional here — SSHError messages are fixed
        # format strings (no subprocess output), see ssh.py docstring.
        print(f"kestra register-system-flows: ssh tunnel failed: {exc}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"kestra register-system-flows: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"kestra register-system-flows: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # Per-flow result lines so the operator sees the POST/PUT detail
    # (e.g. "system.git-sync: created (POST 201)") in the deploy log.
    for flow in result.flows:
        sys.stderr.write(f"  • {flow.name}: {flow.status} ({flow.detail})\n")
    if result.execution_state is not None:
        # Round-2 fix: per-state actionable warning instead of bare enum.
        hint = _kestra_execution_hint(result.execution_state)
        sys.stderr.write(
            f"  • system.flow-sync onboarding execution: {result.execution_state}"
            f"{(' — ' + hint) if hint else ''}\n",
        )
    if result.verify_skipped_reason is not None:
        # Verification step itself didn't complete (transient 5xx /
        # transport blip during flow_exists). State stays SUCCESS but
        # the operator sees that the check wasn't actually run.
        sys.stderr.write(
            f"  • seed-flow visibility check skipped: {result.verify_skipped_reason}\n",
        )

    print(
        f"kestra register-system-flows: "
        f"created={sum(1 for f in result.flows if f.status == 'created')} "
        f"updated={sum(1 for f in result.flows if f.status == 'updated')} "
        f"failed={sum(1 for f in result.flows if f.status == 'failed')} "
        f"execution={result.execution_state or 'skipped'}",
    )
    return 0 if result.is_success else 1


def _gitea_configure(args: list[str]) -> int:
    """`nexus-deploy gitea configure`.

    Opens an SSH port-forward to nexus, runs the synchronous Gitea
    configure flow (DB password sync, admin/user create-or-sync with
    legacy email-collision PATCH, API token create with retry-via-
    delete, workspace repo + collaborator), emits stdout in
    eval-able shell form so the caller can capture the token via:

    .. code-block:: bash

        GITEA_OUT=$(mktemp); python -m nexus_deploy gitea configure > "$GITEA_OUT"
        eval "$(cat "$GITEA_OUT")"  # GITEA_TOKEN=...; RESTART_SERVICES=...
        rm -f "$GITEA_OUT"

    **stdout** (eval-able):
    - ``GITEA_TOKEN=<sha1>`` — only if token was successfully minted
    - ``RESTART_SERVICES=<csv>`` — git-integrated services intersected
      with ``$ENABLED_SERVICES`` (always emitted, may be empty string)

    **stderr**: per-step status lines for the deploy log.

    Reads ``NexusConfig`` from stdin (SECRETS_JSON) and per-deploy
    coordinates from environment variables:

    - ``ADMIN_EMAIL`` — admin's email
    - ``GITEA_USER_EMAIL`` (optional) — regular user's email. Drives the
      legacy email-collision PATCH check on the admin row. The user is
      created/synced ONLY when both this AND ``GITEA_USER_PASS`` are set
      — if either is missing the user-create/sync branch is silently
      skipped.
    - ``GITEA_USER_PASS`` (optional) — see ``GITEA_USER_EMAIL`` above
    - ``REPO_NAME`` — workspace repo name (e.g. nexus-<slug>-gitea)
    - ``GITEA_REPO_OWNER`` — owner of the workspace repo
    - ``ENABLED_SERVICES`` — comma-or-space list driving the
      RESTART_SERVICES intersection
    - ``GH_MIRROR_REPOS`` (optional) — if non-empty, skip repo+collab
      (mirror mode handles repo creation differently)
    - ``GITEA_HOST`` — SSH host alias (default ``nexus``)

    Exit codes:
    - 0: success — admin configured, token minted, repo state OK
    - 1: partial — at least one step failed but token may be in stdout
    - 2: bad args / ssh / unexpected — NO token in stdout
    """
    if args:
        print(f"gitea configure: unknown args {args!r}", file=sys.stderr)
        return 2

    admin_email = os.environ.get("ADMIN_EMAIL") or ""
    repo_name = os.environ.get("REPO_NAME") or ""
    gitea_repo_owner = os.environ.get("GITEA_REPO_OWNER") or ""
    enabled_str = os.environ.get("ENABLED_SERVICES") or ""
    ssh_host = os.environ.get("GITEA_HOST") or "nexus"
    gitea_user_email = os.environ.get("GITEA_USER_EMAIL") or None
    gitea_user_password = os.environ.get("GITEA_USER_PASS") or None
    is_mirror_mode = bool(os.environ.get("GH_MIRROR_REPOS") or "")

    missing = [
        name
        for name, val in (
            ("ADMIN_EMAIL", admin_email),
            ("REPO_NAME", repo_name),
            ("GITEA_REPO_OWNER", gitea_repo_owner),
        )
        if not val
    ]
    if missing:
        print(
            f"gitea configure: missing required env: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    enabled = [s.strip() for s in enabled_str.replace(",", " ").split() if s.strip()]

    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"gitea configure: {exc}", file=sys.stderr)
        return 2

    if not config.gitea_admin_password:
        # Required for both the CLI sync_password and REST basic-auth
        # paths. Without it everything 401s; emit rc=1 so the caller
        # routes to yellow warning, NOT rc=0 (a silent green pass
        # would be the wrong signal here).
        print(
            "gitea configure: GITEA_ADMIN_PASS missing from SECRETS_JSON — "
            "skipping (basic-auth would 401 on every call)",
            file=sys.stderr,
        )
        # Still emit empty RESTART_SERVICES line so eval doesn't
        # leave a stale value from a previous deploy.
        print('RESTART_SERVICES=""')
        return 1

    local_port = _allocate_free_port()

    try:
        with (
            SSHClient(ssh_host) as ssh,
            ssh.port_forward(local_port, "localhost", 3200) as port,
        ):
            result = run_configure_gitea(
                config,
                base_url=f"http://localhost:{port}",
                ssh=ssh,
                admin_email=admin_email,
                gitea_user_email=gitea_user_email,
                gitea_user_password=gitea_user_password,
                repo_name=repo_name,
                gitea_repo_owner=gitea_repo_owner,
                is_mirror_mode=is_mirror_mode,
                enabled_services=enabled,
            )
    except SSHError as exc:
        print(f"gitea configure: ssh tunnel failed: {exc}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"gitea configure: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"gitea configure: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # Per-step status lines on stderr for the deploy log.
    if result.db_pw_synced:
        sys.stderr.write("  • gitea-db password synced\n")
    sys.stderr.write(
        f"  • admin: {result.admin.status}"
        f"{(' — ' + result.admin.detail) if result.admin.detail else ''}\n"
    )
    if result.user is not None:
        sys.stderr.write(
            f"  • user: {result.user.status}"
            f"{(' — ' + result.user.detail) if result.user.detail else ''}\n"
        )
    if result.repo is not None:
        sys.stderr.write(
            f"  • repo: {result.repo.status}"
            f"{(' — ' + result.repo.detail) if result.repo.detail else ''}\n"
        )
    if result.collaborator_added:
        sys.stderr.write("  • collaborator added\n")
    if result.token is None:
        # Always surface the diagnostic — the post-#519 spin-up showed
        # how a silent token-mint failure (no error string in the deploy
        # log) blocks debugging. ``token_error`` is constructed from
        # Gitea CLI error text + return codes, no secrets.
        detail = f" — {result.token_error}" if result.token_error else ""
        sys.stderr.write(f"  • token: NOT minted (downstream skipped){detail}\n")

    # Eval-able stdout. RESTART_SERVICES is always emitted (even
    # empty) so the caller's ``eval`` doesn't leave a stale value
    # from a previous run in the variable. ``shlex.quote`` on every
    # value — Gitea sha1 tokens are 40 hex chars in practice (no
    # special chars), but the explicit quote contract makes
    # injection-safety unambiguous (same convention as #508).
    import shlex as _shlex

    if result.token is not None:
        sys.stdout.write(f"GITEA_TOKEN={_shlex.quote(result.token)}\n")
    sys.stdout.write(f"RESTART_SERVICES={_shlex.quote(','.join(result.restart_services))}\n")

    return 0 if result.is_success else 1


def _gitea_woodpecker_oauth(args: list[str]) -> int:
    """`nexus-deploy gitea woodpecker-oauth`.

    Provisions Gitea's "Woodpecker CI" OAuth2 application. Idempotent
    re-run: deletes any existing app of that name, then creates fresh
    so callers see a known-fresh client_secret on every spin-up
    (Gitea has no rotate-secret API).

    Required env:

    - ``DOMAIN`` — used to build redirect URI ``https://woodpecker.<domain>/authorize``
    - ``GITEA_TOKEN`` — token-bearer auth for the admin user
      (eval-captured from the prior ``gitea configure`` invocation)

    Optional env:

    - ``ADMIN_USERNAME`` — admin username, path-validated (default
      ``admin``). Mirrors :class:`NexusConfig`'s ``admin_username``
      default so the CLI works without an explicit env-passing
      layer when invoked manually.
    - ``GITEA_HOST`` — SSH host alias (default ``nexus``)

    **stdout** (eval-able):

    - ``WOODPECKER_GITEA_CLIENT=<id>``
    - ``WOODPECKER_GITEA_SECRET=<secret>``

    Both lines emitted only when the create succeeds. On failure
    (rc=1), only a stderr diagnostic is emitted; the caller's eval
    sees nothing new and the existing ``.env`` values stay (which
    will be either empty on first run or stale from a prior run).

    Exit codes:

    - 0: created — both env-var lines on stdout, ready to ``eval``
    - 1: partial — list/delete/create REST failure with rotation
      NOT started (Gitea state still consistent with the existing
      Woodpecker .env). Deploy continues without rotating.
    - 2: hard failure — bad args, missing required env, invalid
      ADMIN_USERNAME, SSH tunnel failure, transport/unexpected
      exception, OR rotation half-complete (delete ACK'd or
      possibly applied but create failed; Woodpecker would 401
      until next successful deploy if we continued). Abort.
    """
    if args:
        print(f"gitea woodpecker-oauth: unknown args {args!r}", file=sys.stderr)
        return 2

    domain = os.environ.get("DOMAIN") or ""
    gitea_token = os.environ.get("GITEA_TOKEN") or ""
    admin_username = os.environ.get("ADMIN_USERNAME") or "admin"
    ssh_host = os.environ.get("GITEA_HOST") or "nexus"
    # Issue #540: SUBDOMAIN_SEPARATOR threaded through to the redirect-URI
    # builder. ``"."`` (default) yields ``woodpecker.<domain>/authorize``;
    # multi-tenant forks set ``"-"`` for ``woodpecker-<domain>/authorize``.
    subdomain_separator = (os.environ.get("SUBDOMAIN_SEPARATOR") or ".").strip() or "."

    missing: list[str] = []
    if not domain:
        missing.append("DOMAIN")
    if not gitea_token:
        missing.append("GITEA_TOKEN")
    if missing:
        print(
            f"gitea woodpecker-oauth: missing required env: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    try:
        # Inside the try-block (Copilot R4): _allocate_free_port can
        # raise OSError on ephemeral-port exhaustion. Without this
        # guard the traceback escapes instead of converting to rc=2.
        local_port = _allocate_free_port()
        with (
            SSHClient(ssh_host) as ssh,
            ssh.port_forward(local_port, "localhost", 3200) as port,
        ):
            _ = ssh  # tunnel kept alive for the with-block
            result, error, rotation_started = run_woodpecker_oauth_setup(
                base_url=f"http://localhost:{port}",
                domain=domain,
                gitea_token=gitea_token,
                admin_username=admin_username,
                subdomain_separator=subdomain_separator,
            )
    except SSHError as exc:
        print(f"gitea woodpecker-oauth: ssh tunnel failed: {exc}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"gitea woodpecker-oauth: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except GiteaError as exc:
        # Path-safety violations (unsafe admin_username) and other
        # input-validation failures inside run_woodpecker_oauth_setup
        # surface as GiteaError. Their messages are constructed from
        # fixed format strings + operator-controlled identifiers
        # (no secrets), so safe to surface verbatim. (Copilot R5 —
        # the previous catch-all collapsed these to "unexpected
        # error (GiteaError)" which lost the actionable detail.)
        print(f"gitea woodpecker-oauth: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"gitea woodpecker-oauth: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    if result is None:
        # ``error`` is constructed in :func:`run_woodpecker_oauth_setup`
        # from GiteaError format strings only (HTTP status codes,
        # type names) — never from ``gitea_token``. CodeQL's taint
        # analysis can't prove that and surfaces the line as
        # ``py/clear-text-logging-sensitive-data``. Alert dismissed
        # as "won't fix" with the same rationale (see PR #521).
        sys.stderr.write(f"  • woodpecker-oauth: NOT created — {error}\n")
        # Half-completed rotation = MUST abort. The delete already
        # invalidated the previous client_secret; if we returned
        # rc=1 (yellow warn, deploy continues), Woodpecker would
        # keep running with the now-stale secret in its .env and
        # 401 on every Gitea login until the next deploy succeeds.
        # rc=2 routes the caller to its red-abort branch. (Copilot R2)
        if rotation_started:
            sys.stderr.write(
                "  • rotation half-complete — old creds invalidated, "
                "no fresh ones issued; aborting to avoid a Woodpecker login outage\n",
            )
            return 2
        return 1

    sys.stderr.write("  • woodpecker-oauth: created (fresh client_id + secret)\n")

    import shlex as _shlex

    # Eval-able stdout handoff — same intentional pattern as
    # ``GITEA_TOKEN=`` in :func:`_gitea_configure`. ``shlex.quote``
    # guarantees the value can't break out of the assignment if it
    # ever contains shell metacharacters; the caller writes the
    # eval'd values into Woodpecker's ``.env`` (mode 600) before
    # ``docker compose up -d``. CodeQL flags the secret-bearing line
    # because ``client_secret`` matches its sensitive-name classifier;
    # alert dismissed as "won't fix" — the eval-handoff is the
    # documented contract, mitigated by tempfile mode 600 +
    # trap-driven cleanup of the captured stdout file.
    sys.stdout.write(f"WOODPECKER_GITEA_CLIENT={_shlex.quote(result.client_id)}\n")
    sys.stdout.write(f"WOODPECKER_GITEA_SECRET={_shlex.quote(result.client_secret)}\n")
    return 0


def _gitea_mirror_setup(args: list[str]) -> int:
    """`nexus-deploy gitea mirror-setup`.

    Provisions GH_MIRROR_REPOS as Gitea pull-mirrors plus per-user
    forks. Per-mirror operations:

    1. Migrate (clone-mirror via Gitea's /api/v1/repos/migrate +
       GitHub PAT) — idempotent: already_exists is soft-success
    2. On the FIRST mirror with a configured user: fork into the
       user's namespace via temp user-token (created+deleted
       around the fork POST)
    3. Add the user as read-collaborator on every mirror
    4. On the first iteration where a fork was created/exists:
       trigger mirror-sync + merge-upstream so the fork is
       fast-forwarded from upstream

    Required env:

    - ``GITEA_TOKEN`` — admin's bearer token for migrate / collab /
      mirror-sync (from earlier ``gitea configure`` invocation)
    - ``GH_MIRROR_REPOS`` — comma-separated GitHub repo URLs
    - ``GH_MIRROR_TOKEN`` — GitHub PAT (Contents:read for private
      sources)

    Conditionally required env:

    - ``GITEA_ADMIN_PASS`` — admin password (basic-auth for the
      temp user-token mint inside the fork flow). Required ONLY
      when ``GITEA_USER_USERNAME`` is set; mirrors-only mode
      (no user, no fork) doesn't need it. (Copilot R6)

    Optional env:

    - ``ADMIN_USERNAME`` — admin username, path-validated (default
      ``admin``). Mirrors :class:`NexusConfig`'s ``admin_username``
      default so the CLI works without an explicit env-passing layer
      when invoked manually. (Same default as
      ``gitea woodpecker-oauth`` — Copilot R1 consistency fix.)
    - ``GITEA_USER_USERNAME`` — Gitea username for the per-user fork.
      If unset, the fork step is skipped (mirrors-only mode);
      ``GITEA_ADMIN_PASS`` becomes optional in this case.
    - ``WORKSPACE_BRANCH`` — branch for the merge-upstream step
      (default ``main``). The orchestrator resolves this from the
      GitHub API ahead of time and exports it.
    - ``GITEA_HOST`` — SSH host alias (default ``nexus``)

    **stdout** (eval-able, only when fork was created/exists):

    - ``FORK_NAME=<name>``
    - ``GITEA_REPO_OWNER=<user>``

    These two are consumed by the seed phase so the seed POST hits
    the user's fork rather than the per-iteration mirror name.
    When no fork was created/exists, no stdout output is emitted.

    Exit codes:

    - 0: every mirror succeeded (created or already_exists), fork
      (if attempted) succeeded too
    - 1: at least one mirror failed OR fork failed. Caller keeps
      going (next spin-up retries; mirrors are idempotent).
    - 2: bad args / missing required env / SSH tunnel / unexpected
      exception. Abort.
    """
    if args:
        print(f"gitea mirror-setup: unknown args {args!r}", file=sys.stderr)
        return 2

    admin_username = os.environ.get("ADMIN_USERNAME") or "admin"
    admin_password = os.environ.get("GITEA_ADMIN_PASS") or ""
    gitea_token = os.environ.get("GITEA_TOKEN") or ""
    gh_mirror_repos_csv = os.environ.get("GH_MIRROR_REPOS") or ""
    gh_mirror_token = os.environ.get("GH_MIRROR_TOKEN") or ""
    gitea_user_username = os.environ.get("GITEA_USER_USERNAME") or None
    workspace_branch = os.environ.get("WORKSPACE_BRANCH") or "main"
    ssh_host = os.environ.get("GITEA_HOST") or "nexus"

    missing: list[str] = []
    if not gitea_token:
        missing.append("GITEA_TOKEN")
    if not gh_mirror_repos_csv:
        missing.append("GH_MIRROR_REPOS")
    if not gh_mirror_token:
        missing.append("GH_MIRROR_TOKEN")
    # GITEA_ADMIN_PASS is only consumed by the fork flow's temp
    # user-token mint (basic-auth: admin acts on behalf of user).
    # Mirrors-only mode (no GITEA_USER_USERNAME) doesn't need it.
    # (Copilot R6)
    if gitea_user_username and not admin_password:
        missing.append("GITEA_ADMIN_PASS (required when GITEA_USER_USERNAME is set)")
    if missing:
        print(
            f"gitea mirror-setup: missing required env: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    repos = [s.strip() for s in gh_mirror_repos_csv.split(",") if s.strip()]
    if not repos:
        print("gitea mirror-setup: GH_MIRROR_REPOS contained no repo URLs", file=sys.stderr)
        return 2

    try:
        local_port = _allocate_free_port()
        with (
            SSHClient(ssh_host) as ssh,
            ssh.port_forward(local_port, "localhost", 3200) as port,
        ):
            _ = ssh
            result = run_mirror_setup(
                base_url=f"http://localhost:{port}",
                admin_username=admin_username,
                admin_password=admin_password,
                gitea_token=gitea_token,
                gitea_user_username=gitea_user_username,
                gh_mirror_repos=repos,
                gh_mirror_token=gh_mirror_token,
                workspace_branch=workspace_branch,
            )
    except SSHError as exc:
        print(f"gitea mirror-setup: ssh tunnel failed: {exc}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"gitea mirror-setup: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except GiteaError as exc:
        # Path-safety violations + REST-layer errors not caught by
        # the orchestrator's per-call try/except. Surface verbatim
        # (messages are constructed from format strings only).
        print(f"gitea mirror-setup: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"gitea mirror-setup: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # Per-step status lines on stderr.
    if result.admin_uid is None:
        # Distinguish "admin user genuinely doesn't exist (404)" from
        # auth/transport/5xx failures via admin_uid_error. Without
        # this, the message was misleadingly the same for all paths.
        # (Copilot R4)
        if result.admin_uid_error:
            sys.stderr.write(
                f"  • admin UID lookup failed ({result.admin_uid_error}) — skipping all mirrors\n"
            )
        else:
            sys.stderr.write("  • admin user not found in Gitea — skipping all mirrors\n")
        return 1
    sys.stderr.write(f"  • admin UID: {result.admin_uid}\n")
    for m in result.mirrors:
        sys.stderr.write(
            f"  • mirror: {m.name} → {m.status}{(' — ' + m.detail) if m.detail else ''}\n"
        )
    if result.fork is not None:
        sys.stderr.write(
            f"  • fork: {result.fork.owner}/{result.fork.name} → {result.fork.status}"
            f"{(' — ' + result.fork.detail) if result.fork.detail else ''}\n"
        )
    if result.collaborator_added_count > 0:
        sys.stderr.write(f"  • collaborator added on {result.collaborator_added_count} mirror(s)\n")
    if result.fork_synced:
        sys.stderr.write("  • fork merge-upstream attempted\n")

    # Eval-able stdout: emit FORK_NAME + GITEA_REPO_OWNER iff the
    # fork is in a usable state. The seed phase reads these to point
    # its POST at the user's fork rather than at any iteration's
    # mirror name.
    import shlex as _shlex

    if result.fork is not None and result.fork.status in ("created", "already_exists"):
        sys.stdout.write(f"FORK_NAME={_shlex.quote(result.fork.name)}\n")
        sys.stdout.write(f"GITEA_REPO_OWNER={_shlex.quote(result.fork.owner)}\n")

    return 0 if result.is_success else 1


def _stack_sync(args: list[str]) -> int:
    """`nexus-deploy stack-sync --enabled <comma-list> [--stacks-dir PATH]`.

    Per-stack rsync of ``stacks/<svc>/`` →
    ``nexus:/opt/docker-server/stacks/<svc>/``, plus disabled-stack
    cleanup (server-side ``docker compose down`` + ``rm -rf`` for any
    folder NOT in the enabled list).

    Optional ``--stacks-dir`` defaults to ``stacks`` relative to the
    repo root — exposed for tests. Production callers leave it off.

    Exit codes:

    - 0: every enabled service was either rsynced successfully or
      reported missing-local (kept as soft-success); the cleanup
      script ran and returned RESULT with failed=0.
    - 1: at least one rsync failed OR the cleanup loop reported
      ``failed > 0``, but at least one operation succeeded.
      Yellow warning, continue.
    - 2: bad args, transport (ssh/rsync) failure, no parseable RESULT
      line, or unexpected exception. Caller should abort.
    """
    enabled_str: str | None = None
    stacks_dir_arg: str | None = None
    i = 0
    while i < len(args):
        if args[i] == "--enabled":
            if i + 1 >= len(args):
                print("stack-sync: --enabled requires a value", file=sys.stderr)
                return 2
            enabled_str = args[i + 1]
            i += 2
        elif args[i] == "--stacks-dir":
            if i + 1 >= len(args):
                print("stack-sync: --stacks-dir requires a value", file=sys.stderr)
                return 2
            stacks_dir_arg = args[i + 1]
            i += 2
        else:
            print(f"stack-sync: unknown arg {args[i]!r}", file=sys.stderr)
            return 2

    if enabled_str is None:
        print(
            "stack-sync: --enabled <comma-separated-services> is required",
            file=sys.stderr,
        )
        return 2

    enabled = [s.strip() for s in enabled_str.split(",") if s.strip()]
    if not enabled:
        # Empty list: nothing to rsync, but the cleanup loop still
        # has work — every existing folder on the server is "not in
        # the enabled list" and gets removed. A deploy with zero
        # enabled services therefore tears down every stack on the
        # server, which is the correct semantics.
        pass

    stacks_dir = Path(stacks_dir_arg) if stacks_dir_arg else Path("stacks")
    if not stacks_dir.is_dir():
        print(
            f"stack-sync: stacks dir {stacks_dir!s} is not a directory",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_stack_sync(stacks_dir, enabled)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"stack-sync: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        # Force rc=2 (Python's default rc=1 collides with our
        # partial-failure semantic). Class name only — no str/repr,
        # which could embed secret-bearing values from a future
        # config-aware helper.
        print(f"stack-sync: unexpected error ({type(exc).__name__})", file=sys.stderr)
        return 2

    # Per-service rsync diagnostics on stderr — same pattern as the
    # cleanup script (which streams its own diagnostics). On rsync
    # failure we ALSO surface the captured stderr excerpt as an
    # indented block — Round-2 PR #523 finding: a bare "rc=23"
    # gave operators no actionable signal, the underlying rsync
    # error message ("Permission denied", "No space left on device",
    # "ssh: connect to host nexus port 22: Connection refused", etc.)
    # is what they need to see.
    for r in result.rsync:
        if r.status == "synced":
            sys.stderr.write(f"  ✓ {r.service} synced\n")
        elif r.status == "missing-local":
            sys.stderr.write(f"  ⚠ {r.service}: local stack folder not found - skipping\n")
        else:
            detail = f" ({r.detail})" if r.detail else ""
            sys.stderr.write(f"  ✗ {r.service} rsync failed{detail}\n")
            if r.stderr_excerpt:
                for line in r.stderr_excerpt.splitlines():
                    sys.stderr.write(f"      {line}\n")

    cleanup_summary = (
        f"stopped={result.cleanup.stopped} removed={result.cleanup.removed} "
        f"failed={result.cleanup.failed}"
        if result.cleanup is not None
        else "stopped=? removed=? failed=? (cleanup did not return RESULT)"
    )
    print(
        f"stack-sync: synced={result.synced} missing={result.missing} "
        f"failed_rsync={result.failed_rsync} cleanup: {cleanup_summary}",
    )

    if result.cleanup is None:
        # No parseable RESULT: hard failure (same defensive parse as
        # compose_runner / seeder).
        return 2
    if result.is_success:
        return 0
    # Partial: at least one rsync OR cleanup failure. Distinguish
    # "everything failed" (rc=2) from "some succeeded" (rc=1).
    if result.synced == 0 and result.cleanup.stopped + result.cleanup.removed == 0:
        return 2
    return 1


def _setup_ssh_config(args: list[str]) -> int:
    """`nexus-deploy setup ssh-config`.

    Renders the ``Host nexus`` block in ``~/.ssh/config`` with the
    Cloudflare Access ProxyCommand. Atomic write, mode 0o600.

    Required env: ``SSH_HOST`` (the tunnel hostname),
    ``CF_ACCESS_CLIENT_ID``, ``CF_ACCESS_CLIENT_SECRET``.

    Aborts (rc=2) when either Service Token component is missing —
    browser-login fallback is impossible in CI.

    Exit codes:
    - 0: ssh-config block written
    - 2: missing required env, missing Service Token, or write failure
    """
    if args:
        print(f"setup ssh-config: unknown args {args!r}", file=sys.stderr)
        return 2
    ssh_host = os.environ.get("SSH_HOST", "").strip()
    cf_id = os.environ.get("CF_ACCESS_CLIENT_ID", "").strip() or None
    cf_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "").strip() or None
    if not ssh_host:
        print("setup ssh-config: SSH_HOST env var required", file=sys.stderr)
        return 2
    spec = SSHConfigSpec(ssh_host=ssh_host, cf_client_id=cf_id, cf_client_secret=cf_secret)
    try:
        configure_ssh(spec)
    except SetupError as exc:
        print(f"setup ssh-config: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Filesystem error (permission, disk full, etc.). Class name
        # only so a future bug embedding secrets in the path doesn't
        # leak into the deploy log.
        print(
            f"setup ssh-config: write failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"setup ssh-config: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    auth_mode = "Service Token" if spec.has_service_token else "browser login"
    print(f"setup ssh-config: wrote Host {spec.host_alias} block (auth={auth_mode})")
    return 0


def _setup_wait_ssh(args: list[str]) -> int:
    """`nexus-deploy setup wait-ssh`.

    Polls Cloudflare-Access-tunneled SSH until the host accepts a
    ``BatchMode=yes`` connection.

    When ``CF_ACCESS_CLIENT_ID`` + ``CF_ACCESS_CLIENT_SECRET`` are
    set in the environment, we do the Service Token propagation
    wait first (linear backoff 5/10/15/20/25s after a 10s initial
    sleep). Then the standard SSH-readiness loop (15 retries,
    exponential timeout).

    Optional env: ``SSH_HOST_ALIAS`` (default ``nexus``),
    ``CF_ACCESS_CLIENT_ID``, ``CF_ACCESS_CLIENT_SECRET``.

    Exit codes:
    - 0: SSH connection established
    - 2: max retries exhausted (Token-test OR readiness loop)
    """
    if args:
        print(f"setup wait-ssh: unknown args {args!r}", file=sys.stderr)
        return 2
    host_alias = os.environ.get("SSH_HOST_ALIAS") or "nexus"
    has_token = bool(os.environ.get("CF_ACCESS_CLIENT_ID")) and bool(
        os.environ.get("CF_ACCESS_CLIENT_SECRET"),
    )
    if has_token:
        sys.stderr.write("  Testing Service Token authentication...\n")
        token_result = wait_for_service_token(host_alias=host_alias)
        if not token_result.succeeded:
            sys.stderr.write(
                f"  ✗ Service Token authentication failed after {token_result.attempts} attempts\n",
            )
            if token_result.last_error:
                for line in token_result.last_error.splitlines():
                    sys.stderr.write(f"      {line}\n")
            return 2
        sys.stderr.write(
            f"  ✓ Service Token authentication successful (attempt {token_result.attempts})\n",
        )

    sys.stderr.write("  Waiting for SSH via Cloudflare Tunnel...\n")
    ssh_result = wait_for_ssh(host_alias=host_alias)
    if not ssh_result.succeeded:
        sys.stderr.write(
            f"  ✗ SSH connection failed after {ssh_result.attempts} attempts\n",
        )
        if ssh_result.last_error:
            for line in ssh_result.last_error.splitlines():
                sys.stderr.write(f"      {line}\n")
        return 2
    print(
        f"setup wait-ssh: SSH connection established (attempt {ssh_result.attempts})",
    )
    return 0


def _setup_ensure_jq(args: list[str]) -> int:
    """`nexus-deploy setup ensure-jq`.

    Idempotent ``apt-get install -y jq`` on the remote — bootstrap
    for VMs that pre-date the cloud-init jq install.

    Optional env: ``SSH_HOST_ALIAS`` (default ``nexus``).

    Exit codes:
    - 0: jq present (already-installed or newly-installed)
    - 2: install failed (transport, sudo permission, dpkg lock, etc.)
    """
    if args:
        print(f"setup ensure-jq: unknown args {args!r}", file=sys.stderr)
        return 2
    host_alias = os.environ.get("SSH_HOST_ALIAS") or "nexus"
    try:
        with SSHClient(host_alias) as ssh:
            installed = ensure_jq(ssh)
    except subprocess.CalledProcessError as exc:
        # Round-5 PR #524: jq install failures are usually NOT transport
        # (apt repo down, dpkg lock, missing sudo) — labelling them as
        # such misleads operators. Plus the captured remote output (in
        # exc.output thanks to ssh.run's stdout=PIPE+merge_stderr=True
        # default) carries the actionable error message but was being
        # silently dropped. Now: distinct label + truncated tail
        # forwarded to local stderr. exc.cmd is NOT echoed (defence in
        # depth: a future bug embedding secrets in argv shouldn't leak).
        print(
            f"setup ensure-jq: remote command failed (rc={exc.returncode})",
            file=sys.stderr,
        )
        if exc.output:
            excerpt = exc.output[-2000:].rstrip()
            for line in excerpt.splitlines():
                sys.stderr.write(f"      {line}\n")
        return 2
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"setup ensure-jq: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"setup ensure-jq: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    if installed:
        print("setup ensure-jq: jq newly installed")
    else:
        print("setup ensure-jq: jq already present")
    return 0


# _setup_mount_volume — REMOVED in RFC 0001 cutover. The
# ``nexus-deploy setup mount-volume`` subcommand mounted the
# Hetzner persistent volume at /mnt/nexus-data; persistence
# now lives in R2 via ``s3-restore`` (which writes to the same
# local SSD path, but driven by R2 snapshots, not a block
# volume). Any operator scripts that still call this subcommand
# need to be updated to call ``nexus-deploy s3-snapshot`` for
# the inverse direction (live state → R2).


def _setup_wetty_ssh_agent(args: list[str]) -> int:
    """`nexus-deploy setup wetty-ssh-agent`.

    Renders + runs a server-side bash that:

    1. ssh-keygen the wetty key pair (idempotent — only if absent).
    2. Append the public key to ``authorized_keys`` (idempotent).
    3. Start ``ssh-agent`` with a known socket path (handles
       dead-socket cleanup if the agent crashed previously).
    4. ssh-add the key to the agent (idempotent — fingerprint check).
    5. Write ``SSH_AUTH_SOCK=`` to ``stacks/wetty/.env``.

    Optional env: ``SSH_HOST_ALIAS`` (default ``nexus``).

    Exit codes:
    - 0: all 5 steps completed (whether they were no-ops or made changes)
         AND the .env file was written (i.e. ``auth_sock_written=1``).
         A no-op idempotent run is still rc=0 because the .env append
         is unconditional on the happy path.
    - 1: soft failure — either (a) the script ran but emitted no
         parseable RESULT, or (b) ``auth_sock_written=0`` (the fail-fast
         paths in render_wetty_agent_script emit a parseable
         all-zero RESULT line, so the absence of the .env write is a
         real failure even though the script returned 0). Deploy
         continues since Wetty is non-critical, but the operator sees
         the forwarded stderr.
    - 2: hard transport / unexpected error
    """
    if args:
        print(f"setup wetty-ssh-agent: unknown args {args!r}", file=sys.stderr)
        return 2
    host_alias = os.environ.get("SSH_HOST_ALIAS") or "nexus"
    try:
        with SSHClient(host_alias) as ssh:
            result = setup_wetty_ssh_agent(ssh)
    except subprocess.CalledProcessError as exc:
        # Same defence-in-depth as setup ensure-jq: forward the
        # captured tail to local stderr but DON'T print exc.cmd.
        print(
            f"setup wetty-ssh-agent: remote command failed (rc={exc.returncode})",
            file=sys.stderr,
        )
        if exc.output:
            excerpt = exc.output[-2000:].rstrip()
            for line in excerpt.splitlines():
                sys.stderr.write(f"      {line}\n")
        return 2
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"setup wetty-ssh-agent: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"setup wetty-ssh-agent: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    if result is None:
        print(
            "setup wetty-ssh-agent: script ran but produced no RESULT_WETTY line",
            file=sys.stderr,
        )
        return 1
    # Per-step summary on stdout (workflow log) — same one-line shape
    # as the other setup CLIs.
    parts = []
    if result.keypair_generated:
        parts.append("key-generated")
    if result.pubkey_added:
        parts.append("pubkey-added")
    if result.agent_started:
        parts.append("agent-started")
    if result.key_added_to_agent:
        parts.append("key-added")
    if result.auth_sock_written:
        parts.append("env-written")
    summary = "+".join(parts) if parts else "all-noop"
    print(f"setup wetty-ssh-agent: {summary}")
    # auth_sock_written=0 means render_wetty_agent_script's fail-fast
    # paths fired (ssh-agent unresponsive OR sed/printf to .env failed).
    # Surface as rc=1 so the workflow log shows the soft-fail signal —
    # the caller continues since Wetty is non-critical, but the
    # operator sees that the agent socket isn't actually plumbed
    # through.
    if not result.auth_sock_written:
        print(
            "setup wetty-ssh-agent: soft-fail — SSH_AUTH_SOCK not written "
            "to wetty/.env (Wetty container won't see agent socket)",
            file=sys.stderr,
        )
        return 1
    return 0


def _setup(args: list[str]) -> int:
    """Dispatch ``nexus-deploy setup <subcommand>``."""
    if not args:
        print(
            "setup: subcommand required (ssh-config | wait-ssh | ensure-jq | wetty-ssh-agent)",
            file=sys.stderr,
        )
        return 2
    sub = args[0]
    rest = args[1:]
    if sub == "ssh-config":
        return _setup_ssh_config(rest)
    if sub == "wait-ssh":
        return _setup_wait_ssh(rest)
    if sub == "ensure-jq":
        return _setup_ensure_jq(rest)
    if sub == "wetty-ssh-agent":
        return _setup_wetty_ssh_agent(rest)
    # RFC 0001 cutover: `mount-volume` subcommand removed — see the
    # placeholder comment above _setup_wetty_ssh_agent.
    print(f"setup: unknown subcommand {sub!r}", file=sys.stderr)
    return 2


def _service_env(args: list[str]) -> int:
    """`nexus-deploy service-env --enabled <csv> [--stacks-dir PATH]`.

    Reads ``SECRETS_JSON`` from stdin + ``BootstrapEnv`` fields from
    environment variables, renders the per-service ``.env`` files
    for every enabled service, optionally appends the Gitea
    workspace block to git-integrated stacks (jupyter / marimo /
    code-server / meltano / prefect) when Gitea is enabled and
    the workspace-repo coordinates are provided via env-vars.

    Required env: ``DOMAIN``, ``ADMIN_EMAIL``.
    Optional env (drives the Gitea workspace append):
    ``GITEA_REPO_URL``, ``GITEA_USERNAME``, ``GITEA_PASSWORD``,
    ``GIT_AUTHOR_NAME``, ``GIT_AUTHOR_EMAIL``, ``REPO_NAME``.
    Optional env (BootstrapEnv): ``GITEA_USER_EMAIL``, ``GITEA_USER_USERNAME``,
    ``GITEA_REPO_OWNER``, ``OM_PRINCIPAL_DOMAIN``, ``WOODPECKER_GITEA_CLIENT``,
    ``WOODPECKER_GITEA_SECRET``, ``SSH_KEY_BASE64``.

    Exit codes:
    - 0: every enabled spec rendered (or skipped per its guard)
    - 1: at least one render failed but at least one succeeded
    - 2: hard failure (SFTPGo password missing, write error,
         unexpected exception)
    """
    enabled_str: str | None = None
    stacks_dir_arg: str | None = None
    i = 0
    while i < len(args):
        if args[i] == "--enabled":
            if i + 1 >= len(args):
                print("service-env: --enabled requires a value", file=sys.stderr)
                return 2
            enabled_str = args[i + 1]
            i += 2
        elif args[i] == "--stacks-dir":
            if i + 1 >= len(args):
                print("service-env: --stacks-dir requires a value", file=sys.stderr)
                return 2
            stacks_dir_arg = args[i + 1]
            i += 2
        else:
            print(f"service-env: unknown arg {args[i]!r}", file=sys.stderr)
            return 2
    if enabled_str is None:
        print(
            "service-env: --enabled <comma-separated-services> is required",
            file=sys.stderr,
        )
        return 2
    enabled = [s.strip() for s in enabled_str.split(",") if s.strip()]
    stacks_dir = Path(stacks_dir_arg) if stacks_dir_arg else Path("stacks")
    if not stacks_dir.is_dir():
        print(
            f"service-env: stacks dir {stacks_dir!s} is not a directory",
            file=sys.stderr,
        )
        return 2

    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"service-env: {exc}", file=sys.stderr)
        return 2
    missing = [
        name for name in ("DOMAIN", "ADMIN_EMAIL") if not (os.environ.get(name) or "").strip()
    ]
    if missing:
        print(
            f"service-env: missing required env vars: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    bootstrap_env = BootstrapEnv(
        domain=os.environ.get("DOMAIN") or None,
        admin_email=os.environ.get("ADMIN_EMAIL") or None,
        gitea_user_email=os.environ.get("GITEA_USER_EMAIL") or None,
        gitea_user_username=os.environ.get("GITEA_USER_USERNAME") or None,
        gitea_repo_owner=os.environ.get("GITEA_REPO_OWNER") or None,
        repo_name=os.environ.get("REPO_NAME") or None,
        om_principal_domain=os.environ.get("OM_PRINCIPAL_DOMAIN") or None,
        woodpecker_gitea_client=os.environ.get("WOODPECKER_GITEA_CLIENT") or None,
        woodpecker_gitea_secret=os.environ.get("WOODPECKER_GITEA_SECRET") or None,
        ssh_private_key_base64=os.environ.get("SSH_KEY_BASE64") or None,
    )

    try:
        result = render_all_env_files(config, bootstrap_env, enabled, stacks_dir=stacks_dir)
    except ServiceEnvError as exc:
        print(f"service-env: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"service-env: unexpected error ({type(exc).__name__})", file=sys.stderr)
        return 2

    # Per-service stderr log so operators see what was rendered.
    for r in result.services:
        if r.status == "rendered":
            sys.stderr.write(f"  ✓ {r.service}\n")
        elif r.status == "skipped-not-enabled":
            pass  # too noisy to log every disabled service
        elif r.status == "skipped-guard":
            sys.stderr.write(f"  ⚠ {r.service}: skipped ({r.detail})\n")
        else:
            sys.stderr.write(f"  ✗ {r.service}: {r.detail}\n")

    # Optional: append Gitea workspace block. Driven by env-vars —
    # the orchestrator derives these from mirror/non-mirror logic;
    # we just consume them when present.
    gitea_repo_url = os.environ.get("GITEA_REPO_URL") or ""
    gitea_username = os.environ.get("GITEA_USERNAME") or ""
    gitea_password = os.environ.get("GITEA_PASSWORD") or ""
    git_author_name = os.environ.get("GIT_AUTHOR_NAME") or ""
    git_author_email = os.environ.get("GIT_AUTHOR_EMAIL") or ""
    repo_name = os.environ.get("REPO_NAME") or ""
    # WORKSPACE_BRANCH is OPTIONAL — defaults to 'main' when unset.
    # The orchestrator detects the upstream's default branch in
    # mirror mode and exports it; non-mirrored stacks just stay on
    # 'main'. Direct-CLI invocation without it gets the same default.
    workspace_branch = os.environ.get("WORKSPACE_BRANCH") or "main"
    # Require the full set of workspace coords before appending the
    # block — a partial set would write a broken .env (empty
    # PASSWORD or author fields) that's harder to diagnose than a
    # missing block. The orchestrator derives all six in lockstep,
    # so this is mostly a defence-in-depth check against direct CLI
    # invocation with partial env-vars.
    workspace_coords_complete = all(
        (
            gitea_repo_url,
            gitea_username,
            gitea_password,
            git_author_name,
            git_author_email,
            repo_name,
        ),
    )
    if workspace_coords_complete and "gitea" in enabled:
        cfg = GiteaWorkspaceConfig(
            gitea_repo_url=gitea_repo_url,
            gitea_username=gitea_username,
            gitea_password=gitea_password,
            git_author_name=git_author_name,
            git_author_email=git_author_email,
            repo_name=repo_name,
            workspace_branch=workspace_branch,
        )
        appended = append_gitea_workspace_block(cfg, enabled, stacks_dir=stacks_dir)
        for svc in appended:
            sys.stderr.write(f"  ✓ {svc} Gitea workspace block appended\n")

    print(
        f"service-env: rendered={result.rendered} skipped={result.skipped} failed={result.failed}",
    )
    if result.failed > 0:
        if result.rendered == 0:
            return 2
        return 1
    return 0


def _firewall_configure(args: list[str]) -> int:
    """`nexus-deploy firewall configure --domain <DOMAIN>`.

    Generates the per-service docker-compose firewall overrides used
    to expose TCP ports through the Cloudflare Tunnel, backed by
    :mod:`nexus_deploy.firewall`.

    Reads ``firewall_rules`` JSON from stdin (the Tofu output) and
    writes per-service ``stacks/<svc>/docker-compose.firewall.yml``
    + (when RedPanda has ports) the dual-listener override AND the
    template-substituted ``stacks/redpanda/config/redpanda-firewall.yaml``.

    Exit codes:
    - 0: full success — every artifact written cleanly AND nothing
         was skipped, OR zero-entry mode with no stale-cleanup
         failures.
    - 1: state is inconsistent with what Tofu requested. Several
         distinct conditions all surface as rc=1 because the caller
         treats this exit code as a single 'abort, state is
         inconsistent' branch:
         - At least one per-file write failed but at least one
           succeeded (partial failure).
         - Zero-entry mode but the stale-cleanup pass had per-file
           failures — silent rc=0 here would let stale overrides
           keep host ports exposed contrary to Tofu.
         - At least one service was SKIPPED because its
           ``docker-compose.yml`` was missing or unparseable. The
           service's existing override stays on disk per the safety
           invariant (never delete a still-Tofu-requested override
           on a transient compose error), but the deployed firewall
           may not match Tofu if the operator changed that stack's
           port THIS run.
    - 2: hard error — bad args / unparseable JSON / missing RedPanda
         template file / missing --domain when RedPanda has ports.
         Caller should abort.
    """
    from .firewall import configure as fw_configure

    project_root: Path | None = None
    domain: str | None = None
    i = 0
    while i < len(args):
        if args[i] == "--project-root":
            if i + 1 >= len(args):
                print("firewall configure: --project-root requires a value", file=sys.stderr)
                return 2
            project_root = Path(args[i + 1])
            i += 2
        elif args[i] == "--domain":
            if i + 1 >= len(args):
                print("firewall configure: --domain requires a value", file=sys.stderr)
                return 2
            domain = args[i + 1]
            i += 2
        else:
            print(f"firewall configure: unknown arg {args[i]!r}", file=sys.stderr)
            return 2

    if project_root is None:
        # Default to current working directory — callers invoke from
        # the repo root, where ``stacks/<svc>/...`` is a direct child.
        project_root = Path.cwd()
    if domain is None:
        domain = os.environ.get("DOMAIN", "").strip()

    firewall_json = sys.stdin.read()

    try:
        gen, write = fw_configure(
            firewall_json=firewall_json,
            stacks_dir=project_root,
            domain=domain,
        )
    except ValueError as exc:
        print(f"firewall configure: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"firewall configure: {exc}", file=sys.stderr)
        return 2

    # Even in zero-entry mode, the write/cleanup pass may have failed
    # (e.g. an OSError on stale-cleanup unlink). Surfacing those as
    # rc=1 instead of silently returning 0 is the whole point of #531
    # R1 — without this, a failed remote-cleanup leaves the host port
    # exposed and the workflow finishes green pretending it closed.
    for path, err in write.failed:
        sys.stderr.write(f"  ✗ write failed: {path}: {err}\n")

    if gen.zero_entry:
        if write.failed:
            sys.stderr.write(
                f"firewall configure: zero-entry mode but stale-cleanup had "
                f"{len(write.failed)} failure(s) — aborting so the workflow "
                f"surfaces the inconsistency\n",
            )
            return 1
        print("firewall configure: zero-entry mode (no firewall rules) — no overrides written")
        return 0

    print(
        f"firewall configure: rendered={len(gen.compiled)} "
        f"redpanda={'yes' if gen.redpanda else 'no'} "
        f"skipped={len(gen.skipped)} "
        f"written={len(write.written)} failed={len(write.failed)}",
    )
    for service in gen.skipped:
        sys.stderr.write(
            f"  ✗ skipped {service} (no parseable docker-compose.yml — "
            f"existing override kept on disk per the safety invariant, "
            f"but Tofu's firewall_rules for this stack went unrendered "
            f"this run)\n",
        )

    if write.failed:
        if not write.written:
            return 2
        return 1
    if gen.skipped:
        # rc=1 when ANY service was skipped — the existing
        # docker-compose.firewall.yml stays in place (per the safety
        # invariant from R5 #1: don't delete a still-Tofu-requested
        # override when its compose.yml is transiently unparseable),
        # but the deployed firewall state may not match what Tofu
        # CURRENTLY requests if the operator changed the port for
        # this stack. Surfacing as soft-fail (not rc=2 hard abort)
        # so the caller can decide; rc=1 is the 'state inconsistent
        # with Tofu, abort' signal.
        sys.stderr.write(
            f"firewall configure: {len(gen.skipped)} service(s) skipped — "
            f"deployed firewall state may not match Tofu; surface as rc=1 "
            f"so the workflow doesn't finish green on a stale override\n",
        )
        return 1
    return 0


def _r2_tokens(args: list[str]) -> int:
    """`nexus-deploy r2-tokens <list|cleanup>`.

    Audit + reconciliation utility for Cloudflare R2 user API tokens.
    Surfaces the 50-token-per-account hard cap and lets operators
    proactively delete orphan ``nexus-r2-*`` tokens left behind by
    earlier destroy/setup cycles (see #530 for the bug history).

    Subcommands:

    - ``list``: dry-run inventory. Prints account-wide token total +
      remaining slots + the matched ``nexus-r2-*`` subset. Always
      exit 0; cron / scripts can scrape the output.
    - ``cleanup --name <name>``: delete every token whose name equals
      <name>. Used by re-setup to ensure no orphan exists before
      ``init-r2-state.sh`` mints a fresh token.
    - ``cleanup --prefix <prefix>``: delete every token whose name
      starts with <prefix>. Refuses unless prefix begins with
      ``nexus-r2-`` (defence-in-depth: prevents wiping the
      ``Nexus-Stack`` / ``Nexus2`` / build tokens documented as
      protected in CLAUDE.md).

    Required env: ``TF_VAR_cloudflare_api_token`` (or
    ``CLOUDFLARE_API_TOKEN``).

    Exit codes:
    - 0: ``list`` always returns 0; ``cleanup`` returns 0 only when
         every matched token deleted successfully (or dry-run with no
         per-token attempts). Backed by ``CleanupResult.is_success``.
    - 1: ``cleanup`` completed but at least one per-token delete
         failed (the loop continues — every attempt is reported in
         stdout — but the rc reflects the partial-failure so a
         follow-up cron run can re-attempt).
    - 2: bad args / missing env / network error / API listing failed
         / safety guard hit (e.g. ``--prefix`` doesn't start with
         ``nexus-r2-``).
    """
    if not args:
        print(
            "r2-tokens: subcommand required (list | cleanup --name|--prefix VALUE [--apply])",
            file=sys.stderr,
        )
        return 2

    # Tofu convention is lowercase TF_VAR_*; the upper-case alias is
    # the more common dotenv style. SIM112 wants UPPERCASE only — but
    # the lowercase form is the one Tofu / our setup-control-plane
    # workflow already exports. Honor both with a noqa so SIM112's
    # blanket rule doesn't conflict with the established convention.
    api_token = (
        os.environ.get("TF_VAR_cloudflare_api_token")  # noqa: SIM112
        or os.environ.get("CLOUDFLARE_API_TOKEN")
        or ""
    ).strip()
    if not api_token:
        print(
            "r2-tokens: TF_VAR_cloudflare_api_token (or CLOUDFLARE_API_TOKEN) required",
            file=sys.stderr,
        )
        return 2

    sub = args[0]
    rest = args[1:]

    if sub == "list":
        list_prefix = DEFAULT_NEXUS_R2_PREFIX
        i = 0
        while i < len(rest):
            if rest[i] == "--prefix":
                if i + 1 >= len(rest):
                    print("r2-tokens list: --prefix requires a value", file=sys.stderr)
                    return 2
                list_prefix = rest[i + 1]
                i += 2
            else:
                print(f"r2-tokens list: unknown arg {rest[i]!r}", file=sys.stderr)
                return 2
        try:
            inventory = build_inventory(api_token=api_token, prefix=list_prefix)
        except (RuntimeError, requests.RequestException) as exc:
            print(f"r2-tokens list: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(
            f"r2-tokens list: total={inventory.total} / 50  "
            f"remaining={inventory.remaining_slots}  "
            f"prefix={list_prefix!r}  matched={len(inventory.matched)}",
        )
        if inventory.near_cap:
            sys.stderr.write(
                f"  ⚠ Approaching the 50-token cap (remaining={inventory.remaining_slots})\n",
            )
        for token in inventory.matched:
            issued = token.issued_on or "?"
            print(f"  {token.id}  {issued}  {token.name}")
        return 0

    if sub == "cleanup":
        name: str | None = None
        prefix: str | None = None
        apply_changes = False
        i = 0
        while i < len(rest):
            if rest[i] == "--name":
                if i + 1 >= len(rest):
                    print("r2-tokens cleanup: --name requires a value", file=sys.stderr)
                    return 2
                name = rest[i + 1]
                i += 2
            elif rest[i] == "--prefix":
                if i + 1 >= len(rest):
                    print("r2-tokens cleanup: --prefix requires a value", file=sys.stderr)
                    return 2
                prefix = rest[i + 1]
                i += 2
            elif rest[i] == "--apply":
                apply_changes = True
                i += 1
            else:
                print(f"r2-tokens cleanup: unknown arg {rest[i]!r}", file=sys.stderr)
                return 2
        if (name is None) == (prefix is None):
            print(
                "r2-tokens cleanup: pass exactly one of --name VALUE or --prefix VALUE",
                file=sys.stderr,
            )
            return 2
        try:
            result = cleanup_orphan_tokens(
                api_token=api_token,
                name=name,
                prefix=prefix,
                dry_run=not apply_changes,
            )
        except ValueError as exc:
            # Validation error (e.g. prefix doesn't start with nexus-r2-).
            print(f"r2-tokens cleanup: {exc}", file=sys.stderr)
            return 2
        except (RuntimeError, requests.RequestException) as exc:
            print(f"r2-tokens cleanup: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(
            f"r2-tokens cleanup: total_before={result.total_tokens_before}  "
            f"matched={len(result.matched)}  "
            f"deleted={result.deleted_count}  failed={result.failed_count}  "
            f"dry_run={result.dry_run}",
        )
        for token in result.matched:
            issued = token.issued_on or "?"
            print(f"  matched: {token.id}  {issued}  {token.name}")
        for d in result.deletions:
            status = "OK" if d.deleted else f"FAILED ({d.error})"
            print(f"  delete: {d.id}  {d.name}  {status}")
        if not apply_changes:
            sys.stderr.write(
                "  (dry-run; pass --apply to actually delete)\n",
            )
        return 0 if result.is_success else 1

    print(f"r2-tokens: unknown subcommand {sub!r}", file=sys.stderr)
    return 2


def _run_all(args: list[str]) -> int:
    """`nexus-deploy run-all`.

    Calls every module function in sequence with in-process state
    handoff, then emits 3 values to stdout for the surviving shell
    glue to ``eval``:

    - ``RESTART_SERVICES=<csv>`` — compose-restart loop input
    - ``WOODPECKER_GITEA_CLIENT=<id>`` — written into stacks/woodpecker/.env
    - ``WOODPECKER_GITEA_SECRET=<secret>`` — written into stacks/woodpecker/.env

    Other state (GITEA_TOKEN, FORK_NAME, FORK_OWNER) is consumed
    entirely inside the orchestrator and never exits Python.

    Required env: ``ADMIN_EMAIL``, ``REPO_NAME``, ``GITEA_REPO_OWNER``,
    ``ENABLED_SERVICES``, ``DOMAIN``, ``PROJECT_ID``, ``INFISICAL_TOKEN``.
    Optional env: ``WORKSPACE_BRANCH`` (default ``main``),
    ``GH_MIRROR_REPOS``, ``GH_MIRROR_TOKEN``, ``GITEA_USER_USERNAME``,
    ``GITEA_USER_EMAIL``, ``GITEA_USER_PASS``, ``OM_PRINCIPAL_DOMAIN``,
    ``INFISICAL_ENV`` (default ``dev``), ``SSH_HOST_ALIAS`` (default ``nexus``).

    Exit codes:
    - 0: every phase ok or skipped
    - 1: at least one phase produced status='partial'
    - 2: at least one phase failed (orchestrator aborted)
    """
    if args:
        print(f"run-all: unknown args {args!r}", file=sys.stderr)
        return 2

    admin_email = os.environ.get("ADMIN_EMAIL") or ""
    repo_name = os.environ.get("REPO_NAME") or ""
    gitea_repo_owner = os.environ.get("GITEA_REPO_OWNER") or ""
    enabled_str = os.environ.get("ENABLED_SERVICES") or ""
    domain = os.environ.get("DOMAIN") or ""
    project_id = os.environ.get("PROJECT_ID") or ""
    infisical_token = os.environ.get("INFISICAL_TOKEN") or ""

    missing = [
        name
        for name, val in (
            ("ADMIN_EMAIL", admin_email),
            ("REPO_NAME", repo_name),
            ("GITEA_REPO_OWNER", gitea_repo_owner),
            ("ENABLED_SERVICES", enabled_str),
            ("DOMAIN", domain),
            ("PROJECT_ID", project_id),
            ("INFISICAL_TOKEN", infisical_token),
        )
        if not val
    ]
    if missing:
        print(f"run-all: missing required env: {', '.join(missing)}", file=sys.stderr)
        return 2

    enabled = [s.strip() for s in enabled_str.replace(",", " ").split() if s.strip()]
    workspace_branch = os.environ.get("WORKSPACE_BRANCH") or "main"
    gh_mirror_repos_csv = os.environ.get("GH_MIRROR_REPOS") or ""
    gh_mirror_token = os.environ.get("GH_MIRROR_TOKEN") or None
    gitea_user_username = os.environ.get("GITEA_USER_USERNAME") or None
    gitea_user_email = os.environ.get("GITEA_USER_EMAIL") or None
    gitea_user_password = os.environ.get("GITEA_USER_PASS") or None
    ssh_host = os.environ.get("SSH_HOST_ALIAS") or "nexus"
    infisical_env = os.environ.get("INFISICAL_ENV") or "dev"
    gh_mirror_repos = [s.strip() for s in gh_mirror_repos_csv.split(",") if s.strip()]
    # Inputs for the post-bootstrap phases (compose-restart,
    # kestra-secret-sync, woodpecker-apply, mirror-seed-rerun,
    # mirror-finalize):
    admin_username = os.environ.get("ADMIN_USERNAME") or ""
    woodpecker_agent_secret = os.environ.get("WOODPECKER_AGENT_SECRET") or None

    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"run-all: {exc}", file=sys.stderr)
        return 2
    bootstrap_env = BootstrapEnv(
        domain=domain,
        admin_email=admin_email,
        gitea_user_email=gitea_user_email,
        gitea_user_username=gitea_user_username,
        gitea_repo_owner=gitea_repo_owner,
        repo_name=repo_name,
        om_principal_domain=os.environ.get("OM_PRINCIPAL_DOMAIN") or None,
        woodpecker_gitea_client=os.environ.get("WOODPECKER_GITEA_CLIENT") or None,
        woodpecker_gitea_secret=os.environ.get("WOODPECKER_GITEA_SECRET") or None,
        ssh_private_key_base64=os.environ.get("SSH_KEY_BASE64") or None,
    )

    orchestrator = Orchestrator(
        config=config,
        bootstrap_env=bootstrap_env,
        enabled_services=enabled,
        repo_name=repo_name,
        gitea_repo_owner=gitea_repo_owner,
        workspace_branch=workspace_branch,
        gh_mirror_repos=gh_mirror_repos,
        gh_mirror_token=gh_mirror_token,
        gitea_user_username=gitea_user_username,
        gitea_user_email=gitea_user_email,
        gitea_user_password=gitea_user_password,
        ssh_host=ssh_host,
        project_id=project_id,
        infisical_token=infisical_token,
        infisical_env=infisical_env,
        domain=domain,
        admin_username=admin_username,
        woodpecker_agent_secret=woodpecker_agent_secret,
    )

    try:
        result = orchestrator.run_all()
    except SSHError as exc:
        print(f"run-all: ssh setup failed: {exc}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"run-all: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"run-all: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # Per-phase log to stderr.
    for phase in result.phases:
        marker = {"ok": "✓", "partial": "⚠", "failed": "✗", "skipped": "—"}.get(phase.status, "?")
        detail = f" — {phase.detail}" if phase.detail else ""
        sys.stderr.write(f"  {marker} {phase.name}: {phase.status}{detail}\n")

    # Eval-able stdout: 3 values for the surviving shell glue.
    import shlex as _shlex

    # Always emit all 3 lines so a previous run's shell vars don't
    # leak into the next deploy via `eval` reading a stale value
    # when a phase skipped or failed early.
    sys.stdout.write(
        f"RESTART_SERVICES={_shlex.quote(','.join(result.state.restart_services))}\n",
    )
    sys.stdout.write(
        f"WOODPECKER_GITEA_CLIENT={_shlex.quote(result.state.woodpecker_client_id or '')}\n",
    )
    sys.stdout.write(
        f"WOODPECKER_GITEA_SECRET={_shlex.quote(result.state.woodpecker_client_secret or '')}\n",
    )

    if result.has_hard_failure:
        return 2
    if result.has_partial:
        return 1
    return 0


# PR #537 R2 #3+#4: simplified — capture the quoted value via a named
# ``value`` group (callers no longer need to ``split('"', 2)[1]`` the
# whole match) and collapse the trail to just ``(?P<trail>.*)``. The
# previous ``(?:#|//).*|.*`` alternation was redundant — ``.*`` matches
# everything anyway, so the explicit comment-form alternative didn't
# constrain anything.
_TFVARS_TYPE_LINE = re.compile(
    r'^(?P<lead>\s*server_type\s*=\s*)"(?P<value>[^"\n\r]*)"(?P<trail>.*)$',
    re.MULTILINE,
)
_TFVARS_LOC_LINE = re.compile(
    r'^(?P<lead>\s*server_location\s*=\s*)"(?P<value>[^"\n\r]*)"(?P<trail>.*)$',
    re.MULTILINE,
)
_TFVARS_PREFS_LINE = re.compile(
    r'^\s*server_preferences\s*=\s*"(?P<value>[^"\n\r]*)"',
    re.MULTILINE,
)


def _read_preferences_from_tfvars(text: str) -> str | None:
    """Return the value of ``server_preferences = "..."`` if present.

    Returns ``None`` when the key is absent (or only ``server_type`` /
    ``server_location`` are present — the legacy single-pair shorthand
    is reconstructed by the caller from those keys).
    """
    match = _TFVARS_PREFS_LINE.search(text)
    return match.group("value") if match is not None else None


def _read_single_pair_from_tfvars(text: str) -> _hetzner.ServerSpec | None:
    """Return the legacy ``server_type`` + ``server_location`` pair
    from a tfvars file, or ``None`` if either is missing.

    Used as the back-compat shim when ``server_preferences`` isn't
    set: an existing operator with ``vars.SERVER_TYPE`` + ``vars.
    SERVER_LOCATION`` set should keep working without having to
    learn the new key.
    """
    type_match = _TFVARS_TYPE_LINE.search(text)
    loc_match = _TFVARS_LOC_LINE.search(text)
    if type_match is None or loc_match is None:
        return None
    # PR #537 R2 #3: use the named ``value`` capture group instead of
    # ``match.group(0).split('"', 2)[1]`` — same semantics, but the
    # intent (extract the quoted value) is now explicit in the regex.
    # PR #537 R8 #3: ``.strip()`` before ``.lower()``. A hand-edited
    # tfvars like ``server_location = "hel1 "`` (with stray trailing
    # whitespace inside the quotes) would otherwise produce a
    # ServerSpec with location='hel1 ' that never matches the
    # whitespace-stripped Hetzner location keys → confusing 'unknown
    # location' diagnostic for what is actually a copy-paste artefact.
    type_value = type_match.group("value").strip()
    loc_value = loc_match.group("value").strip()
    if not type_value or not loc_value:
        return None
    return _hetzner.ServerSpec(
        server_type=type_value.lower(),
        location=loc_value.lower(),
    )


def _rewrite_tfvars_pair(text: str, selected: _hetzner.ServerSpec) -> str:
    """Rewrite the ``server_type`` and ``server_location`` lines in a
    tfvars body to the selected pair.

    Trailing inline comments are preserved (the regex captures and
    re-emits them). If a key is absent the function appends it as a
    fresh line at the end — so an operator who only configured
    ``server_preferences`` (no single-pair shorthand) still ends up
    with the legacy keys in place for ``tofu apply`` to consume.
    """
    new_type_line = f'server_type = "{selected.server_type}"'
    new_loc_line = f'server_location = "{selected.location}"'

    # PR #537 R1 #1: re-emit the captured ``trail`` group so trailing
    # inline comments (``server_type = "cx43" # primary``) survive the
    # rewrite. Previous version dropped everything after the closing
    # quote, silently deleting hand-written context.
    if _TFVARS_TYPE_LINE.search(text):
        text = _TFVARS_TYPE_LINE.sub(
            lambda m: f'{m.group("lead")}"{selected.server_type}"{m.group("trail")}',
            text,
            count=1,
        )
    else:
        # PR #537 R4 #4: rstrip("\r\n") instead of rstrip("\n") so a
        # CRLF-line-ending file (rare in this project but possible if
        # an operator hand-edits config.tfvars on Windows) doesn't
        # leave a stray ``\r`` before our appended LF.
        text = text.rstrip("\r\n") + "\n" + new_type_line + "\n"

    if _TFVARS_LOC_LINE.search(text):
        text = _TFVARS_LOC_LINE.sub(
            lambda m: f'{m.group("lead")}"{selected.location}"{m.group("trail")}',
            text,
            count=1,
        )
    else:
        text = text.rstrip("\r\n") + "\n" + new_loc_line + "\n"

    return text


def _select_capacity(args: list[str]) -> int:
    """`nexus-deploy select-capacity` (Issue #536).

    Pre-flight step that runs in spin-up.yml BEFORE ``tofu apply``:
    walks an operator-provided preference list of ``<server_type>:
    <location>`` pairs, queries Hetzner Cloud's API
    (``/v1/server_types`` to resolve type name → ID, then
    ``/v1/datacenters`` for the per-DC ``available`` list keyed by
    those IDs), and rewrites ``config.tfvars`` to the first pair
    that is in stock. Lets a deploy survive a Hetzner capacity
    crunch by transparently falling through to the next region
    without operator intervention. (PR #537 R4 #3 — docstring
    corrected to mention both endpoints; the previous text only
    listed ``/v1/datacenters`` which made API-permission debugging
    harder.)

    Preference source priority (first non-empty wins):

    1. ``SERVER_PREFERENCES`` env var (passed via spin-up.yml from
       the ``vars.SERVER_PREFERENCES`` repo variable). Used as-is —
       the operator-provided list IS the full list, no fallback
       appended (this is the "expert override" path).
    2. ``server_preferences = "..."`` line in ``config.tfvars``.
       Same as #1: used verbatim, no fallback.
    3. Legacy single-pair shorthand: ``server_type = "..."`` +
       ``server_location = "..."`` lines in ``config.tfvars``.
       The class-config write-path lands here. The operator's pair
       is used as the FIRST preference, then
       :data:`hetzner_capacity.DEFAULT_PREFERENCES` is appended as
       fallback (deduplicated). This way a single sold-out region
       for the configured type doesn't fail the spin-up; the
       deploy transparently falls through to the next region or
       tier.
    4. :data:`hetzner_capacity.DEFAULT_PREFERENCES` (nothing
       configured anywhere).

    Required env: ``HCLOUD_TOKEN``. Without it the step exits 0 with
    a stderr warning — capacity-selection is opportunistic; a local-
    dev or CI dry-run that doesn't talk to Hetzner should be free to
    skip.

    Required positional: ``--tfvars PATH`` to the config.tfvars file
    that will be rewritten in place.

    Exit codes:

    - 0: a pair was selected (or skipped due to missing token)
    - 2: preference list exhausted, or API failure, or arg error
    """
    # Crude arg-parse — keeps us out of argparse for one-flag handlers.
    tfvars_path: Path | None = None
    i = 0
    while i < len(args):
        if args[i] == "--tfvars":
            # PR #537 R1 #2: explicit branch for the missing-value case
            # so the operator sees a specific error instead of the
            # generic "unknown arg '--tfvars'" that the fall-through
            # would produce.
            if i + 1 >= len(args):
                print(
                    "select-capacity: --tfvars requires a value (path to config.tfvars)",
                    file=sys.stderr,
                )
                return 2
            tfvars_path = Path(args[i + 1])
            i += 2
            continue
        print(f"select-capacity: unknown arg {args[i]!r}", file=sys.stderr)
        return 2
    if tfvars_path is None:
        print("select-capacity: --tfvars PATH is required", file=sys.stderr)
        return 2
    if not tfvars_path.is_file():
        print(f"select-capacity: {tfvars_path} not found", file=sys.stderr)
        return 2

    # ``TF_VAR_hcloud_token`` (lowercase suffix) is the real env-var
    # name spin-up.yml exports today — Tofu's ``TF_VAR_<name>``
    # convention requires the suffix to match the variable name in
    # variables.tf, which is lowercase here. Lint's all-caps rule
    # is silenced via the inline directive; the name is dictated by
    # Tofu, not us.
    # PR #537 R1 #3: ``.strip()`` so a stray trailing newline (common
    # when the env var was sourced from a file) doesn't end up inside
    # the Bearer header → would cause a hard-to-diagnose HTTP 401.
    token = (
        os.environ.get("HCLOUD_TOKEN")
        or os.environ.get("TF_VAR_hcloud_token")  # noqa: SIM112
        or ""
    ).strip()
    if not token:
        sys.stderr.write(
            "⚠ select-capacity: HCLOUD_TOKEN not set; skipping capacity check "
            "(deploy will use whatever pair is already in config.tfvars)\n",
        )
        return 0

    # Resolve preferences in priority order.
    text = tfvars_path.read_text(encoding="utf-8")
    raw_prefs = os.environ.get("SERVER_PREFERENCES", "").strip()
    if not raw_prefs:
        from_file = _read_preferences_from_tfvars(text)
        if from_file is not None and from_file.strip():
            raw_prefs = from_file
    preferences: tuple[_hetzner.ServerSpec, ...]
    if raw_prefs:
        try:
            preferences = _hetzner.parse_preferences(raw_prefs)
        except ValueError as exc:
            print(f"select-capacity: {exc}", file=sys.stderr)
            return 2
    else:
        legacy_pair = _read_single_pair_from_tfvars(text)
        if legacy_pair is not None:
            # Class-config shorthand: operator's choice FIRST, then
            # DEFAULT_PREFERENCES (dedup'd) so a single sold-out region
            # for the configured type doesn't abort the spin-up.
            default_specs = _hetzner.parse_preferences(
                ",".join(_hetzner.DEFAULT_PREFERENCES),
            )
            seen: set[tuple[str, str]] = {(legacy_pair.server_type, legacy_pair.location)}
            extended: list[_hetzner.ServerSpec] = [legacy_pair]
            for spec in default_specs:
                key = (spec.server_type, spec.location)
                if key in seen:
                    continue
                seen.add(key)
                extended.append(spec)
            preferences = tuple(extended)
            sys.stderr.write(
                f"select-capacity: no server_preferences set; using legacy "
                f"single-pair shorthand from config.tfvars ({legacy_pair}) "
                f"as primary, then DEFAULT_PREFERENCES as fallback "
                f"({len(preferences)} entries total)\n",
            )
        else:
            preferences = _hetzner.parse_preferences(",".join(_hetzner.DEFAULT_PREFERENCES))
            sys.stderr.write(
                "select-capacity: no server_preferences / server_type+location set; "
                "using built-in default list\n",
            )

    try:
        availability = _hetzner.fetch_availability(token)
    except _hetzner.HetznerCapacityError as exc:
        print(f"select-capacity: Hetzner API failure: {exc}", file=sys.stderr)
        return 2

    selected = _hetzner.select(preferences, availability)
    status_lines = _hetzner.render_status_lines(preferences, availability, selected)

    if selected is None:
        # PR #537 R7 #1: distinguish "every preference has an unknown
        # location" (operator typo) from "every preference is genuinely
        # out of stock" (capacity crunch). The two cases need different
        # operator actions: fix the typo vs widen / wait. When MIXED
        # (some unknown + some sold out), the per-pair status block
        # above already tells the operator which is which via the
        # ``?`` vs ``✗`` markers, and the generic out-of-stock guidance
        # still applies as the dominant action.
        unknown_specs = [s for s in preferences if s.location not in availability]
        if len(unknown_specs) == len(preferences):
            sys.stderr.write(
                "✗ select-capacity: none of the preferred locations are known to Hetzner — "
                "almost certainly a typo. Per-pair status:\n",
            )
            for line in status_lines:
                sys.stderr.write(line + "\n")
            unknown_list = ", ".join(str(s) for s in unknown_specs)
            sys.stderr.write(
                f"Unknown locations: {unknown_list}. "
                "Hetzner location names are lowercase like fsn1 / nbg1 / hel1 / ash. "
                "Check `SERVER_PREFERENCES` (repo variable) or the "
                "`server_preferences` line in config.tfvars for typos.\n",
            )
            return 2
        sys.stderr.write(
            "✗ select-capacity: every preference is out of stock at Hetzner.\n"
            "Per-pair availability:\n",
        )
        for line in status_lines:
            sys.stderr.write(line + "\n")
        sys.stderr.write(
            "Either widen the preference list — set `SERVER_PREFERENCES` repo "
            "variable (highest priority) or the `server_preferences` line in "
            "config.tfvars to a longer comma list — or wait. Hetzner stock "
            "fluctuates hour by hour. Recommended fallback order: cx43, cx53, "
            "cpx42, cpx52, cpx62 across hel1/fsn1/nbg1 (the built-in default). "
            "Check live stock per region in the Hetzner Cloud Console "
            "(https://console.hetzner.cloud/) — the create-server UI greys out "
            "out-of-stock combinations.\n",
        )
        return 2

    sys.stderr.write(f"✓ select-capacity: chose {selected}\n")
    for line in status_lines:
        sys.stderr.write(line + "\n")

    new_text = _rewrite_tfvars_pair(text, selected)
    if new_text != text:
        # Atomic replace — write to sibling tempfile + rename. Survives
        # a crash mid-write without leaving config.tfvars half-rewritten.
        tmp = tfvars_path.with_suffix(tfvars_path.suffix + ".select-capacity.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(tfvars_path)
    return 0


def _run_pipeline(args: list[str]) -> int:
    """`nexus-deploy run-pipeline`.

    Top-level deploy entrypoint. Calls
    :func:`nexus_deploy.pipeline.run_pipeline` which orchestrates:

    - R2 credentials env-injection from ``tofu/.r2-credentials``
    - ``tofu state list`` pre-flight
    - config.tfvars parse + Gitea identity derivation
    - 6 ``tofu output`` reads
    - ssh-keygen -R cleanup
    - setup chain (configure_ssh / wait_for_ssh / ensure_jq) +
      ``s3_restore.restore_from_s3`` (RFC 0001 cutover)
    - Optional Docker Hub login + Wetty SSH-Agent setup
    - ``Orchestrator.run_pre_bootstrap``
    - ``Orchestrator.run_all``
    - Service URLs banner

    All in-process — no subprocess CLI invocations of nexus_deploy
    sub-commands, no eval-able stdout payloads.

    Required env: none (everything is read from tofu state +
    config.tfvars).

    Optional env (workflow secrets, all forwarded via
    :class:`PipelineOptions`):
    - ``SSH_PRIVATE_KEY_CONTENT`` — base64-encoded into BootstrapEnv
    - ``GH_MIRROR_TOKEN`` + ``GH_MIRROR_REPOS`` — for mirror-mode
    - ``DOCKERHUB_USER`` + ``DOCKERHUB_TOKEN`` — for higher pull rate
    - ``INFISICAL_ENV`` — defaults to "dev"
    - ``PROJECT_ROOT`` — defaults to ``$PWD``; the repo checkout root

    Exit codes:
    - 0: deploy succeeded — covers both clean runs AND runs where
         one or more phases reported ``status='partial'``. Partial
         is surfaced as a stderr warning, NOT a non-zero exit, so
         spin-up.yml's ``shell: bash -e`` step doesn't fail the
         workflow on a soft warning. (Tightened in PR #535 R0/R1.)
    - 2: hard failure (PipelineError; tofu state missing, secrets
         empty, ssh wait timeout, orchestrator phase status='failed').
    """
    if args:
        print(f"run-pipeline: unknown args {args!r}", file=sys.stderr)
        return 2

    project_root_env = os.environ.get("PROJECT_ROOT")
    project_root = Path(project_root_env) if project_root_env else Path.cwd()

    options = _pipeline.PipelineOptions(
        ssh_private_key_content=os.environ.get("SSH_PRIVATE_KEY_CONTENT") or None,
        gh_mirror_token=os.environ.get("GH_MIRROR_TOKEN") or None,
        gh_mirror_repos=os.environ.get("GH_MIRROR_REPOS") or None,
        dockerhub_user=os.environ.get("DOCKERHUB_USER") or None,
        dockerhub_token=os.environ.get("DOCKERHUB_TOKEN") or None,
        infisical_env=os.environ.get("INFISICAL_ENV") or "dev",
    )

    try:
        result = _pipeline.run_pipeline(project_root=project_root, options=options)
    except _pipeline.PipelineError as exc:
        print(f"run-pipeline: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        # PR #535 R1 #6: include rc + stderr/stdout tail so CI failures
        # are diagnosable without re-running with --debug. Don't print
        # ``exc.cmd`` — it can carry secrets via env-var-prefixed forms.
        tail = (exc.stderr or exc.stdout or "")[-500:].rstrip()
        print(
            f"run-pipeline: subprocess failed (rc={exc.returncode})"
            + (f": {tail}" if tail else ""),
            file=sys.stderr,
        )
        return 2
    except subprocess.TimeoutExpired as exc:
        # No rc on timeout (the process didn't exit), but ``timeout``
        # tells the operator how long we waited.
        print(
            f"run-pipeline: subprocess timed out after {exc.timeout}s ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except SetupError as exc:
        # Setup-helper-specific errors (configure_ssh / wait_for_ssh /
        # ensure_jq / setup_wetty_ssh_agent) carry a clear message —
        # surface it directly.
        print(f"run-pipeline: setup step failed: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            f"run-pipeline: OS error ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"run-pipeline: unexpected error ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 2

    # Per-phase log to stderr — operators need visibility into which
    # phases ran/skipped/failed/partialled. The Orchestrator records
    # PhaseResult into result.phases but never emits stderr lines of
    # its own; without this loop a successful run-pipeline shows only
    # the compose-up "started and running" markers + the done banner,
    # masking secret-sync / git-sync / kestra-secret-sync failures
    # that surfaced via PhaseResult(status='partial' or 'failed').
    # Mirror the legacy ``_run_pre_bootstrap`` / ``_run_all`` handlers.
    markers = {"ok": "✓", "partial": "⚠", "failed": "✗", "skipped": "—"}
    for label, sub_result in (
        ("pre-bootstrap", result.pre_bootstrap),
        ("run-all", result.run_all),
    ):
        sys.stderr.write(f"\n[{label}]\n")
        for phase in sub_result.phases:
            marker = markers.get(phase.status, "?")
            detail = f" — {phase.detail}" if phase.detail else ""
            sys.stderr.write(f"  {marker} {phase.name}: {phase.status}{detail}\n")

    sys.stdout.write(_pipeline.format_done_banner(result))

    # Exit-code dispatch: a successful deploy returns 0 — even when
    # one or more phases produced ``status='partial'``. The
    # individual ``run-all`` / ``run-pre-bootstrap`` handlers return
    # rc=1 for partial when called as standalone subcommands so
    # callers can branch on it. ``run-pipeline`` is the top-level
    # CLI invoked directly by spin-up.yml's bash with ``set -e``, so
    # a non-zero exit fails the workflow step. Partial is a "warn
    # and continue" semantic surfaced via the per-phase stderr log;
    # only actual hard failures (PipelineError, raised above) get
    # the rc=2 treatment.
    has_partial = result.pre_bootstrap.has_partial or result.run_all.has_partial
    if has_partial:
        sys.stderr.write(
            "\nNote: one or more phases reported status='partial' "
            "(see per-phase log above) — deploy succeeded with warnings.\n",
        )
    return 0


def _s3_snapshot(args: list[str]) -> int:
    """`nexus-deploy s3-snapshot`.

    Push the current persistent state to R2 atomically, before
    ``tofu destroy``. The teardown workflow MUST call this and
    fail-fast on non-zero exit; running ``tofu destroy`` against
    an unverified snapshot would lose student data.

    Required env (only when the feature flag is on):
    - ``NEXUS_S3_PERSISTENCE`` (gate; exact ``"true"`` opts in)
    - ``PERSISTENCE_S3_ENDPOINT`` / ``PERSISTENCE_S3_REGION`` /
      ``PERSISTENCE_S3_BUCKET`` (the R2 coords)
    - ``R2_ACCESS_KEY_ID`` / ``R2_SECRET_ACCESS_KEY``
    - ``PERSISTENCE_STACK_SLUG`` (manifest field; bucket-name shape).
      The teardown workflow injects this from
      ``${{ secrets.PERSISTENCE_STACK_SLUG || github.event.repository.name }}``
      so operators get a sensible CI fallback without code in this
      handler. Local CLI invocations MUST set it explicitly — no
      filesystem-side default applies.
    - ``PERSISTENCE_TEMPLATE_VERSION`` (manifest field; release tag).
      Workflow-injected from ``github.ref_name``; required for local
      CLI invocations.

    Optional env:
    - ``PROJECT_ROOT`` — defaults to ``$PWD``; the repo checkout root

    Exit codes:
    - 0: snapshot applied OR a legitimate no-op (teardown proceeds):
         * feature flag off (nothing to snapshot; stack hasn't opted
           in to S3 persistence)
         * no Tofu state to snapshot (issue #564: partial deploy —
           setup-control-plane succeeded but spin-up aborted before
           any ``tofu apply`` ran, so there's nothing on the server
           to back up; subsequent ``tofu destroy`` is also a no-op)
    - 2: hard failure — pipeline pre-flight, SSH wait timeout,
         CalledProcessError from the rendered bash, or feature flag
         on with credentials missing. Teardown MUST abort.
    """
    if args:
        print(f"s3-snapshot: unknown args {args!r}", file=sys.stderr)
        return 2

    # When the feature flag is off, return 0 without reading any
    # other env or touching SSH — stacks that haven't opted in
    # should never hit the SSH-setup / tofu-state preflight just
    # because the workflow now always invokes this subcommand.
    if not _s3_restore.is_enabled():
        return 0

    stack_slug = os.environ.get("PERSISTENCE_STACK_SLUG", "").strip()
    template_version = os.environ.get("PERSISTENCE_TEMPLATE_VERSION", "").strip()
    if not stack_slug or not template_version:
        missing = [
            name
            for name, val in (
                ("PERSISTENCE_STACK_SLUG", stack_slug),
                ("PERSISTENCE_TEMPLATE_VERSION", template_version),
            )
            if not val
        ]
        print(
            f"s3-snapshot: required env vars unset or empty: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    project_root_env = os.environ.get("PROJECT_ROOT")
    project_root = Path(project_root_env) if project_root_env else Path.cwd()

    try:
        result = _pipeline.run_snapshot(
            project_root=project_root,
            stack_slug=stack_slug,
            template_version=template_version,
        )
    except _pipeline.PipelineError as exc:
        print(f"s3-snapshot: {exc}", file=sys.stderr)
        return 2
    except _s3_persistence.S3PersistenceError as exc:
        # Structural validation failures from s3_persistence (bad
        # endpoint charset, bucket-name shape, bad rsync subpath,
        # etc.) — operator-actionable: surface a targeted message
        # before the generic catch-all turns it into "unexpected
        # error". Must come BEFORE the broad Exception handler.
        print(f"s3-snapshot: invalid S3 persistence config: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        # Atomicity contract: a remote-script failure (rclone drift,
        # pg_dump error, compose-stop error) MUST abort the teardown.
        # Surface a diagnostic tail without leaking cmd (which can
        # carry env-var-prefixed secrets — same rule as run-pipeline).
        tail = (exc.stderr or exc.stdout or "")[-500:].rstrip()
        print(
            f"s3-snapshot: remote script failed (rc={exc.returncode})"
            + (f": {tail}" if tail else ""),
            file=sys.stderr,
        )
        return 2
    except SetupError as exc:
        print(f"s3-snapshot: setup step failed: {exc}", file=sys.stderr)
        return 2
    except SSHError as exc:
        print(f"s3-snapshot: ssh failure: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            f"s3-snapshot: OS error ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"s3-snapshot: unexpected error ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 2

    outcome = result.outcome
    if isinstance(outcome, _s3_restore.S3SnapshotApplied):
        sys.stderr.write(
            f"✓ s3-snapshot: applied snapshot {outcome.timestamp}\n",
        )
        return 0
    # Skipped — branch on reason. feature_flag_off is unreachable
    # here (filtered above) but kept for symmetry.
    if outcome.reason == "feature_flag_off":
        return 0
    if outcome.reason == "no_state_to_snapshot":
        # Issue #564: partially-deployed fork (setup-control-plane
        # succeeded, spin-up aborted before any tofu apply). Nothing
        # on the server to snapshot; teardown should proceed.
        sys.stderr.write(
            "s3-snapshot: stack has no Tofu state - nothing to snapshot "
            "(partial deploy?). Teardown will proceed.\n",
        )
        return 0
    # no_endpoint_env — snapshot_to_s3 already wrote its own
    # diagnostic listing the missing env vars. Map to rc=2.
    return 2


def _run_pre_bootstrap(args: list[str]) -> int:
    """`nexus-deploy run-pre-bootstrap`.

    Runs the pre-bootstrap pipeline (service-env →
    firewall-configure → stack-sync → compose-up →
    infisical-provision) in a single Python invocation. (Phase
    order: PR #532 R5 #1 fixed an issue where firewall overrides
    were rendered after stack-sync ran, so they never made it onto
    the server.)

    Reads ``SECRETS_JSON`` from stdin (Tofu output). Reads workspace
    coords + firewall_rules + admin password from env vars.

    On rc=0 emits eval-able stdout for the caller:
    ``INFISICAL_TOKEN=<token>`` + ``PROJECT_ID=<id>`` (the two values
    downstream phases need). Empty values on rc=1 (provision
    soft-fail) so ``eval`` clears any stale value.

    SECURITY: stdout carries an Infisical bearer token. The CALLER
    MUST redirect stdout to a file (or pipe through ``eval``) so the
    token doesn't end up in workflow logs / terminal scrollback. The
    typical pattern is::

        OUT=$(mktemp); trap 'rm -f "$OUT"' EXIT
        run-pre-bootstrap > "$OUT" || RC=$?
        eval "$(cat "$OUT")"

    DON'T invoke this command interactively without a redirection.
    Same eval-pattern + redirection conventions as
    ``infisical provision-admin``.

    Required env: ``ADMIN_EMAIL``, ``ENABLED_SERVICES``, ``DOMAIN``,
    ``ADMIN_USERNAME``, ``INFISICAL_PASS``, ``FIREWALL_RULES_JSON`` —
    explicit, NOT defaulted (PR #532 R5 #2): a missing/empty value
    would otherwise be silently treated as zero-entry mode by the
    firewall module and trigger destructive cleanup of existing
    override files. Operators MUST pass an explicit ``"{}"`` to opt
    into zero-entry mode.

    Optional env: ``REPO_NAME``, ``GITEA_REPO_OWNER`` (now derived
    by ``_phase_workspace_coords``; can be pre-seeded for tests),
    ``WORKSPACE_BRANCH`` (default ``main``),
    ``GITEA_USER_USERNAME``, ``GITEA_USER_EMAIL``, ``GITEA_USER_PASS``,
    ``GITEA_ADMIN_PASS``, ``USER_EMAIL`` (passed into global-env's
    stacks/.env), ``GH_MIRROR_REPOS`` (csv), ``GH_MIRROR_TOKEN``
    (gates default-branch detection), ``IMAGE_VERSIONS_JSON`` (default
    ``"{}"``; consumed by the global-env phase),
    ``OM_PRINCIPAL_DOMAIN``, ``SSH_HOST_ALIAS`` (default ``nexus``),
    ``PROJECT_ROOT`` (default ``$PWD``) — the repo checkout root;
    phases derive ``$PROJECT_ROOT/stacks`` for per-service compose paths.
    (Renamed from ``STACKS_DIR`` in PR #532 R2 #1.)

    Exit codes:
    - 0: every phase ok or skipped.
    - 1: at least one phase produced status='partial' (caller
         continues — operator sees the per-phase log).
    - 2: at least one phase failed (orchestrator aborted; subsequent
         steps that depend on Infisical/etc must abort too).
    """
    if args:
        print(f"run-pre-bootstrap: unknown args {args!r}", file=sys.stderr)
        return 2

    admin_email = os.environ.get("ADMIN_EMAIL") or ""
    repo_name = os.environ.get("REPO_NAME") or ""
    gitea_repo_owner = os.environ.get("GITEA_REPO_OWNER") or ""
    enabled_str = os.environ.get("ENABLED_SERVICES") or ""
    domain = os.environ.get("DOMAIN") or ""
    admin_password_infisical = os.environ.get("INFISICAL_PASS") or ""
    # PR #532 R5 #2: FIREWALL_RULES_JSON is required (no default).
    # An accidental empty value would be treated by the firewall module
    # as intentional zero-entry mode and trigger destructive cleanup of
    # existing override files on disk. Operators must pass "{}" explicitly
    # to opt into zero-entry mode.
    firewall_json = os.environ.get("FIREWALL_RULES_JSON") or ""
    # Inputs for the workspace-coords + firewall-sync + global-env phases:
    admin_username = os.environ.get("ADMIN_USERNAME") or ""
    user_email = os.environ.get("USER_EMAIL") or ""
    gitea_admin_pass = os.environ.get("GITEA_ADMIN_PASS") or None
    image_versions_json = os.environ.get("IMAGE_VERSIONS_JSON") or "{}"
    gh_mirror_repos_csv = os.environ.get("GH_MIRROR_REPOS") or ""
    gh_mirror_token = os.environ.get("GH_MIRROR_TOKEN") or None

    # Build a list of variable NAMES that are missing/empty. CodeQL's
    # 'clear-text logging of sensitive information' rule scans for
    # password-typed values reaching log statements; rename to
    # `missing_names` so the comprehension makes it obvious that only
    # the (name) projection — not the (val) — gets emitted to stderr.
    # Caught in PR #532 R1 #1 (CodeQL false positive).
    #
    # REPO_NAME + GITEA_REPO_OWNER are NOT required:
    # _phase_workspace_coords derives them from raw inputs. They can
    # still be passed for back-compat / pre-seeding (e.g. tests).
    required_env = (
        ("ADMIN_EMAIL", admin_email),
        ("ENABLED_SERVICES", enabled_str),
        ("DOMAIN", domain),
        ("ADMIN_USERNAME", admin_username),
        ("INFISICAL_PASS", admin_password_infisical),
        ("FIREWALL_RULES_JSON", firewall_json),
    )
    missing_names = [name for name, val in required_env if not val]
    if missing_names:
        print(
            f"run-pre-bootstrap: missing required env: {', '.join(missing_names)}",
            file=sys.stderr,
        )
        return 2

    enabled = [s.strip() for s in enabled_str.replace(",", " ").split() if s.strip()]
    workspace_branch = os.environ.get("WORKSPACE_BRANCH") or "main"
    gitea_user_username = os.environ.get("GITEA_USER_USERNAME") or None
    gitea_user_email = os.environ.get("GITEA_USER_EMAIL") or None
    gitea_user_password = os.environ.get("GITEA_USER_PASS") or None
    ssh_host = os.environ.get("SSH_HOST_ALIAS") or "nexus"
    project_root_env = os.environ.get("PROJECT_ROOT")
    project_root = Path(project_root_env) if project_root_env else Path.cwd()

    try:
        config = NexusConfig.from_secrets_json(sys.stdin.read())
    except ConfigError as exc:
        print(f"run-pre-bootstrap: {exc}", file=sys.stderr)
        return 2

    bootstrap_env = BootstrapEnv(
        domain=domain,
        admin_email=admin_email,
        gitea_user_email=gitea_user_email,
        gitea_user_username=gitea_user_username,
        gitea_repo_owner=gitea_repo_owner,
        repo_name=repo_name,
        om_principal_domain=os.environ.get("OM_PRINCIPAL_DOMAIN") or None,
    )

    gh_mirror_repos = [s.strip() for s in gh_mirror_repos_csv.split(",") if s.strip()]
    orchestrator = Orchestrator(
        config=config,
        bootstrap_env=bootstrap_env,
        enabled_services=enabled,
        repo_name=repo_name,
        gitea_repo_owner=gitea_repo_owner,
        workspace_branch=workspace_branch,
        gh_mirror_repos=gh_mirror_repos,
        gh_mirror_token=gh_mirror_token,
        gitea_user_username=gitea_user_username,
        gitea_user_email=gitea_user_email,
        gitea_user_password=gitea_user_password,
        ssh_host=ssh_host,
        domain=domain,
        firewall_json=firewall_json,
        project_root=project_root,
        admin_password_infisical=admin_password_infisical,
        # workspace-coords + global-env inputs:
        admin_username=admin_username,
        user_email=user_email,
        gitea_admin_pass=gitea_admin_pass,
        image_versions_json=image_versions_json,
    )

    try:
        result = orchestrator.run_pre_bootstrap()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"run-pre-bootstrap: transport failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"run-pre-bootstrap: unexpected error ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    # Per-phase log to stderr.
    for phase in result.phases:
        marker = {"ok": "✓", "partial": "⚠", "failed": "✗", "skipped": "—"}.get(phase.status, "?")
        detail = f" — {phase.detail}" if phase.detail else ""
        sys.stderr.write(f"  {marker} {phase.name}: {phase.status}{detail}\n")

    # Eval-able stdout: 5 values for the caller. Always emit (with
    # empty values when not populated) so ``eval`` clears stale
    # shell vars from prior runs. The 3 workspace-coords lines
    # (REPO_NAME, GITEA_REPO_OWNER, WORKSPACE_BRANCH) come from the
    # workspace-coords phase.
    import shlex as _shlex

    sys.stdout.write(
        f"INFISICAL_TOKEN={_shlex.quote(result.state.infisical_token or '')}\n",
    )
    sys.stdout.write(
        f"PROJECT_ID={_shlex.quote(result.state.project_id or '')}\n",
    )
    sys.stdout.write(
        f"REPO_NAME={_shlex.quote(result.state.repo_name or '')}\n",
    )
    sys.stdout.write(
        f"GITEA_REPO_OWNER={_shlex.quote(result.state.gitea_repo_owner or '')}\n",
    )
    sys.stdout.write(
        f"WORKSPACE_BRANCH={_shlex.quote(result.state.workspace_branch or 'main')}\n",
    )

    if result.has_hard_failure:
        return 2
    if result.has_partial:
        return 1
    return 0


def _allocate_free_port() -> int:
    """Ask the kernel for a free IPv4 ephemeral port on the loopback.

    Bind a socket to ``127.0.0.1:0`` (kernel picks free), record the
    assigned port, immediately close. The returned port is then handed
    to ``ssh -L 127.0.0.1:<port>:…`` to re-bind. Race window between
    close and ssh-rebind is microseconds; for production-deploy-
    frequency that's fine. If a future contributor needs zero-race,
    paramiko's port-forward has a callback API but we explicitly chose
    subprocess + system ssh, so this is the right primitive.

    Note: IPv4-only by design. ``ssh.SSHClient.port_forward`` matches
    by passing the explicit ``127.0.0.1:`` bind address — without it,
    ssh on a dual-stack host would also bind ``::1`` and a port that
    looked free here could still be taken on IPv6, causing intermittent
    ExitOnForwardFailure aborts (round-4 PR #517 finding).
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


# Hints emitted alongside execution_state in stderr — actionable
# replacements for the bare-enum output, one warning per case.
_KESTRA_EXECUTION_HINTS: dict[str, str] = {
    "SUCCESS": "",
    "FAILED": "open the execution in the Kestra UI for the error log",
    "KILLED": "open the execution in the Kestra UI for the error log",
    "RUNNING": "did not complete within the timeout — first regular cron tick will retry within 15 min",
    "CREATED": "execution stuck in CREATED state — check Kestra worker logs",
    "UNKNOWN": "execution state could not be determined — check Kestra UI",
    "TRIGGER_FAILED": "could not trigger execution — first sync will run on the next 15-min cron tick",
    "SEED_FLOW_MISSING": "system.flow-sync ran but the seeded flow is not visible — "
    "check that nexus_seeds/kestra/flows/r2-taxi-pipeline.yaml is in the workspace repo "
    "and re-execute system.flow-sync from the Kestra UI",
}


def _kestra_execution_hint(state: str) -> str:
    """Return the actionable warning string for a given ExecutionState."""
    return _KESTRA_EXECUTION_HINTS.get(state, "")


def main() -> int:
    """Subcommand dispatcher. See the module docstring for the full
    list of subcommands.
    """
    args = sys.argv[1:]
    if args == ["--version"]:
        print(__version__)
        return 0
    if args in ([], ["hello"]):
        print(hello())
        return 0
    if args[:2] == ["config", "dump-shell"]:
        return _config_dump_shell(args[2:])
    if args[:2] == ["infisical", "bootstrap"]:
        return _infisical_bootstrap(args[2:])
    if args[:2] == ["infisical", "provision-admin"]:
        return _infisical_provision_admin(args[2:])
    if args[:1] == ["secret-sync"]:
        return _secret_sync(args[1:])
    if args[:1] == ["seed"]:
        return _seed(args[1:])
    if args[:1] == ["compose"]:
        return _compose_up(args[1:])
    if args[:1] == ["services"]:
        return _services_configure(args[1:])
    if args[:2] == ["kestra", "register-system-flows"]:
        return _kestra_register_system_flows(args[2:])
    if args[:2] == ["gitea", "configure"]:
        return _gitea_configure(args[2:])
    if args[:2] == ["gitea", "woodpecker-oauth"]:
        return _gitea_woodpecker_oauth(args[2:])
    if args[:2] == ["gitea", "mirror-setup"]:
        return _gitea_mirror_setup(args[2:])
    if args[:1] == ["stack-sync"]:
        return _stack_sync(args[1:])
    if args[:1] == ["setup"]:
        return _setup(args[1:])
    if args[:1] == ["service-env"]:
        return _service_env(args[1:])
    if args[:1] == ["run-all"]:
        return _run_all(args[1:])
    if args[:1] == ["run-pre-bootstrap"]:
        return _run_pre_bootstrap(args[1:])
    if args[:1] == ["select-capacity"]:
        return _select_capacity(args[1:])
    if args[:1] == ["run-pipeline"]:
        return _run_pipeline(args[1:])
    if args[:1] == ["s3-snapshot"]:
        return _s3_snapshot(args[1:])
    if args[:1] == ["r2-tokens"]:
        return _r2_tokens(args[1:])
    if args[:2] == ["firewall", "configure"]:
        return _firewall_configure(args[2:])
    print(
        f"nexus_deploy {__version__}: unknown command {' '.join(args)!r}",
        file=sys.stderr,
    )
    print(
        "Available: --version, hello, "
        "config dump-shell [--tofu-dir PATH (default: tofu/stack) | --stdin], "
        "infisical bootstrap (reads SECRETS_JSON from stdin + env vars), "
        "infisical provision-admin (env: ADMIN_EMAIL + INFISICAL_PASS; emits "
        "INFISICAL_TOKEN + PROJECT_ID), "
        "secret-sync --stack <jupyter|marimo|kestra>, "
        "seed --repo <owner>/<name> [--root PATH] [--prefix nexus_seeds/], "
        "compose up --enabled <comma-list>, "
        "services configure --enabled <comma-list> (reads SECRETS_JSON from stdin), "
        "kestra register-system-flows (reads SECRETS_JSON from stdin + env vars), "
        "gitea configure (reads SECRETS_JSON from stdin + env vars; emits eval-able stdout), "
        "gitea woodpecker-oauth (env-only; emits WOODPECKER_GITEA_CLIENT + WOODPECKER_GITEA_SECRET), "
        "gitea mirror-setup (env-only; emits FORK_NAME + GITEA_REPO_OWNER iff a fork was provisioned), "
        "stack-sync --enabled <comma-list> [--stacks-dir PATH], "
        "setup ssh-config | wait-ssh | ensure-jq | wetty-ssh-agent, "
        "service-env --enabled <comma-list> [--stacks-dir PATH] (reads SECRETS_JSON from stdin), "
        "run-all (reads SECRETS_JSON from stdin + env vars; emits eval-able stdout: "
        "RESTART_SERVICES + WOODPECKER_GITEA_CLIENT + WOODPECKER_GITEA_SECRET), "
        "run-pre-bootstrap (workspace-coords → service-env → firewall-configure → "
        "stack-sync → firewall-sync → global-env → compose-up → infisical-provision; reads "
        "SECRETS_JSON from stdin + env vars incl. INFISICAL_PASS, FIREWALL_RULES_JSON, "
        "ADMIN_USERNAME, IMAGE_VERSIONS_JSON; emits eval-able stdout: INFISICAL_TOKEN + "
        "PROJECT_ID + REPO_NAME + GITEA_REPO_OWNER + WORKSPACE_BRANCH), "
        "select-capacity --tfvars PATH (Issue #536: pre-flight Hetzner capacity "
        "check; reads HCLOUD_TOKEN + optional SERVER_PREFERENCES env, walks "
        "<type>:<location> preference list, rewrites server_type+server_location "
        "in PATH to first available pair; rc=2 if every preference is out of stock), "
        "run-pipeline (top-level deploy entry; reads tofu state + "
        "config.tfvars; optional env: SSH_PRIVATE_KEY_CONTENT, "
        "GH_MIRROR_TOKEN, GH_MIRROR_REPOS, DOCKERHUB_USER, DOCKERHUB_TOKEN, "
        "INFISICAL_ENV, PROJECT_ROOT), "
        "s3-snapshot (teardown-side; reads NEXUS_S3_PERSISTENCE + 5 PERSISTENCE_S3_*/R2_* "
        "env vars + PERSISTENCE_STACK_SLUG + PERSISTENCE_TEMPLATE_VERSION; rc=0 when flag "
        "off or snapshot applied, rc=2 on any failure — teardown MUST abort), "
        "r2-tokens list [--prefix STR] | cleanup --name|--prefix VALUE [--apply] "
        "(env: TF_VAR_cloudflare_api_token), "
        "firewall configure [--project-root PATH] [--domain DOMAIN] "
        "(reads firewall_rules JSON from stdin)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
