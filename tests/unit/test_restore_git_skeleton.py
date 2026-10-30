"""A restored git repository must still be a git repository.

R2 keeps objects, not directories, so a filesystem snapshot loses every
empty directory. A bare repository whose refs are all packed — every pull
mirror, and any repository after ``git gc`` — has an empty ``refs/heads``
and ``refs/tags``, so it came back without ``refs/`` and git, and Forgejo
with it, refused it: "The Git data underlying this repository cannot be
read". Seen on DEADS8 for the course-repository mirror after the first
teardown and spin-up.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from nexus_deploy import s3_restore
from nexus_deploy.s3_persistence import (
    RsyncTarget,
    S3Endpoint,
    _render_git_skeleton_repair,
    render_restore_script,
)


def _endpoint() -> S3Endpoint:
    return S3Endpoint(
        endpoint="https://abc123.r2.cloudflarestorage.com",
        region="auto",
        access_key="AKIA1234",
        secret_key="secret123",
        bucket="nexus-test",
    )


def test_forgejo_and_gitea_repo_trees_are_marked_as_git_repositories() -> None:
    _, rsync = s3_restore.standard_targets()
    marked = {t.name for t in rsync if t.git_repos}
    assert marked == {"forgejo-repos", "gitea-repos"}


def test_restore_repairs_only_the_git_trees_and_after_their_sync() -> None:
    repos = RsyncTarget(
        name="forgejo-repos", local_path="/mnt/r", s3_subpath="forgejo/repos", git_repos=True
    )
    lfs = RsyncTarget(name="forgejo-lfs", local_path="/mnt/l", s3_subpath="forgejo/lfs")
    script = render_restore_script(
        endpoint=_endpoint(), postgres_targets=(), rsync_targets=(repos, lfs)
    )

    sync = script.index('rclone sync "$BUCKET/$SNAPSHOT_PREFIX/forgejo/repos" /mnt/r')
    repair = script.index("find /mnt/r -type d -name '*.git'")
    assert sync < repair
    assert "find /mnt/l" not in script


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git to build a real mirror")
def test_repair_makes_a_packed_mirror_readable_again(tmp_path: Path) -> None:
    def git(*args: str, cwd: Path = tmp_path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    git("init", "-q", "src")
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=tmp_path / "src")
    tree = tmp_path / "repos" / "nexus"
    tree.mkdir(parents=True)
    git("clone", "-q", "--mirror", str(tmp_path / "src"), str(tree / "mirror.git"))
    git("pack-refs", "--all", cwd=tree / "mirror.git")

    # What a round trip through R2 leaves: every empty directory gone.
    for d in sorted((p for p in tree.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    assert not (tree / "mirror.git" / "refs").exists()
    assert git("rev-parse", "HEAD", cwd=tree / "mirror.git").returncode != 0

    # A directory named like a repo but without HEAD must stay untouched.
    (tree / "notes.git").mkdir()

    script = "\n".join(_render_git_skeleton_repair(str(tmp_path / "repos")))
    subprocess.run(["bash", "-euo", "pipefail", "-c", script], check=True)

    assert git("rev-parse", "HEAD", cwd=tree / "mirror.git").returncode == 0
    for sub in ("refs/heads", "refs/tags", "objects/info", "objects/pack"):
        assert (tree / "mirror.git" / sub).is_dir()
    assert list((tree / "notes.git").iterdir()) == []

    # Idempotent: a second run on an intact repository changes nothing.
    subprocess.run(["bash", "-euo", "pipefail", "-c", script], check=True)
    assert git("rev-parse", "HEAD", cwd=tree / "mirror.git").returncode == 0
