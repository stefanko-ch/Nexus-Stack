"""Launcher for every Streamlit app on this server.

Streamlit serves one entrypoint script per process. This is that script:
it walks the directories listed in ``_sources()``, builds an ``st.Page``
for each ``.py`` file it finds, and hands the result to
``st.navigation``, which renders the sidebar and runs whichever page the
user picked.

The walk happens on every rerun, so a file added to one of those
directories shows up after a browser refresh — no container restart, no
redeploy.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

# Bind-mounted from stacks/streamlit/apps/ in the deployment repository.
EXAMPLES_ROOT = Path("/srv/apps")

# Where the entrypoint clones the Forgejo workspace repository. Deliberately
# NOT under EXAMPLES_ROOT and deliberately not the repository root: that
# repository holds Kestra flows, marimo notebooks and dbt models too, and a
# recursive scan of all of it would list every one of them as a Streamlit app
# and then fail when somebody clicked one.
WORKSPACE_ROOT = Path("/srv/workspace")

# The two places inside the workspace repository that are scanned, relative
# to its root. The first is where the seeded examples land, the second is for
# apps a user adds themselves.
WORKSPACE_SUBDIRS = ("nexus_seeds/streamlit", "streamlit")


def _title(path: Path) -> str:
    """A readable label from a file name: ``sales_by_region.py`` -> ``Sales by region``."""
    words = path.stem.replace("-", " ").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else path.stem


def _sources() -> list[tuple[str, Path]]:
    """The directories to scan, each with its sidebar heading."""
    sources = [("Examples", EXAMPLES_ROOT)]
    repo_name = os.environ.get("REPO_NAME", "")
    if repo_name:
        for subdir in WORKSPACE_SUBDIRS:
            sources.append(("Workspace", WORKSPACE_ROOT / repo_name / subdir))
    return sources


def _discover() -> dict[str, list[st.Page]]:
    """Group the discovered apps under their source's heading."""
    sections: dict[str, list[st.Page]] = {}
    # Pre-claimed by the welcome page below. An app file called `home.py`
    # would otherwise resolve to the same url_path and shadow it.
    seen: set[str] = {"home"}

    for label, root in _sources():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(root)
            # Helper modules, by the same underscore convention the marimo
            # seeds use — importable by an app, not an app themselves.
            if any(part.startswith((".", "_")) for part in relative.parts):
                continue
            # The URL path has to be unique across every source, and the file
            # name alone is not: two directories may both hold a `report.py`.
            url_path = str(relative.with_suffix("")).replace("/", "_")
            if url_path in seen:
                url_path = f"{label.lower()}_{url_path}"
            seen.add(url_path)
            sections.setdefault(label, []).append(
                # Absolute paths are explicitly supported by st.Page ("It can
                # be absolute or relative to the entrypoint file"), which is
                # what lets the apps live outside this file's directory.
                st.Page(path, title=_title(path), url_path=url_path)
            )
    return sections


def _welcome() -> None:
    """The landing page, and what a server with no apps at all shows."""
    st.title("Streamlit")
    st.write(
        "This server runs every app it finds in the directories below. "
        "Pick one from the sidebar, or add your own."
    )
    st.markdown(
        "**Workspace** — commit a `.py` file to `streamlit/` in the workspace "
        "repository (Forgejo). It is cloned when this stack starts, so restart "
        "the stack from the Control Plane after pushing.\n\n"
        "**Examples** — what ships with Nexus-Stack, in "
        "`stacks/streamlit/apps/` of the deployment repository."
    )
    st.caption(
        "Files and directories whose name starts with an underscore are treated "
        "as helper modules and are not listed."
    )


navigation: dict[str, list[st.Page]] = {
    "Start": [st.Page(_welcome, title="Home", url_path="home", default=True)]
}
navigation.update(_discover())

st.navigation(navigation).run()
