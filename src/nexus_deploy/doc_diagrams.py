"""Generate the diagrams in ``docs/concepts/assets/`` and ``docs/admin-guides/assets/``.

Four pictures for the concept pages, each answering one question a newcomer has:

* ``nexus-stack-in-one-picture.svg`` — who does what when I click?
* ``lifecycle.svg`` — what survives a teardown?
* ``request-path.svg`` — why is no port open?
* ``three-planes.svg`` — which parts are there, and where does state live?

Three for the snapshot-lifecycle guide, each for a mechanism that is hard to
hold in your head from prose (#657):

* ``snapshot-teardown-order.svg`` — why the teardown does things in this order
* ``snapshot-credential-epoch.svg`` — why an old snapshot can be refused
* ``snapshot-spin-up-decision.svg`` — "cannot tell" is not "there is none"

They replace three hand-drawn SVGs that had gone stale without anyone
noticing: two still said "61 stacks" and one showed a persistent volume that
``tofu/stack/main.tf`` no longer creates. A picture cannot be grepped, so the
text in these lives in this module, where it can.

Rules the drawings follow:

* one question per picture and as few elements as it takes;
* plain language, product names only where a reader will recognise them;
* no number that can go stale — no stack count, no server price;
* colour means the plane: blue is the control plane and Cloudflare, amber is
  GitHub Actions and anything that happens only on request, green is your
  server, grey is everything else;
* each picture carries its own dark background, so it looks the same in
  GitHub's light and dark themes and on the website.

Regenerate after changing this module::

    uv run python -m nexus_deploy.doc_diagrams

``tests/unit/test_doc_diagrams.py`` fails when a committed SVG differs from
what this module renders.

Icons: the outline icons are from Tabler Icons (MIT licence), the GitHub mark
is from Simple Icons (CC0).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

BG = "#0e1318"
CARD = "#161d24"
TEXT = "#f2f5f7"
SUB = "#a9b4bf"
GREY = "#8291a0"
BLUE = "#4aa8ff"  # control plane, Cloudflare
AMBER = "#f5a524"  # GitHub Actions; "only on request"
GREEN = "#34d399"  # your server
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

# 24x24 icon paths. Outline icons are stroked, the GitHub mark is filled.
_OUTLINE_ICONS: dict[str, tuple[str, ...]] = {
    "user": (
        "M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0",
        "M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2",
    ),
    "browser": (
        "M4 8h16",
        "M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z",
        "M8 4v4",
    ),
    "server": (
        "M3 4m0 3a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3z",
        "M3 12m0 3a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3z",
        "M7 8l0 .01",
        "M7 16l0 .01",
    ),
    "lock": (
        "M5 13a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v6a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2v-6z",
        "M11 16a1 1 0 1 0 2 0a1 1 0 0 0 -2 0",
        "M8 11v-4a4 4 0 1 1 8 0v4",
    ),
    "database": (
        "M12 6m-8 0a8 3 0 1 0 16 0a8 3 0 1 0 -16 0",
        "M4 6v6a8 3 0 0 0 16 0v-6",
        "M4 12v6a8 3 0 0 0 16 0v-6",
    ),
}
_GITHUB_MARK = (
    "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 "
    "0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 "
    "3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 "
    "1.835 2.809 1.305 "
    "3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 "
    "0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 "
    "1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 "
    "3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 "
    "5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 "
    ".315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
)

_MARKERS = (("b", BLUE), ("o", AMBER), ("g", GREEN), ("x", GREY))


def _text(
    x: float,
    y: float,
    lines: str | list[str],
    size: float = 16,
    fill: str = TEXT,
    weight: int = 400,
    anchor: str = "middle",
    leading: float = 1.3,
) -> str:
    rows = [lines] if isinstance(lines, str) else lines
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else size * leading}">{escape(row)}</tspan>'
        for i, row in enumerate(rows)
    )
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
        f'text-anchor="{anchor}">{spans}</text>'
    )


def _icon(name: str, cx: float, cy: float, colour: str, scale: float = 1.6) -> str:
    """Draw a 24x24 icon centred on (cx, cy)."""
    origin = f"translate({cx - 12 * scale} {cy - 12 * scale}) scale({scale})"
    if name == "github":
        return f'<path transform="{origin}" fill="{colour}" d="{_GITHUB_MARK}"/>'
    paths = "".join(f'<path d="{d}"/>' for d in _OUTLINE_ICONS[name])
    return (
        f'<g transform="{origin}" fill="none" stroke="{colour}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</g>'
    )


def _svg(width: int, height: int, title: str, subtitle: str, label: str, body: str) -> str:
    markers = "".join(
        f'<marker id="arrow-{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{colour}"/></marker>'
        for key, colour in _MARKERS
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label={quoteattr(label)} font-family="{FONT}">'
        f"<title>{escape(label)}</title><defs>{markers}</defs>"
        f'<rect width="{width}" height="{height}" rx="18" fill="{BG}"/>'
        + _text(36, 50, title, 26, TEXT, 700, "start")
        + _text(36, 78, subtitle, 16, SUB, 400, "start")
        + body
        + "</svg>\n"
    )


def one_picture() -> str:
    """Who does what when I click?"""
    xs = (110, 310, 510, 710)
    nodes = (
        ("user", GREY, TEXT, "You", ["click in", "the browser"]),
        ("browser", BLUE, BLUE, "Control Plane", ["remembers", "what you want"]),
        ("github", AMBER, AMBER, "GitHub Actions", ["builds it,", "every time"]),
        ("server", GREEN, GREEN, "Your server", ["runs your", "stacks"]),
    )
    y = 180
    body = ""
    for x, (icon, ring, name_colour, name, sub) in zip(xs, nodes, strict=True):
        body += f'<circle cx="{x}" cy="{y}" r="44" fill="{CARD}" stroke="{ring}" stroke-width="3"/>'
        body += _icon(icon, x, y, ring)
        body += _text(x, y + 76, name, 19, name_colour, 700) + _text(x, y + 100, sub, 15, SUB)
    arrows = (
        ("enable, spin up", BLUE, "b"),
        ("starts a workflow", AMBER, "o"),
        ("creates, deploys", GREEN, "g"),
    )
    for i, (label, colour, key) in enumerate(arrows):
        x1, x2 = xs[i] + 52, xs[i + 1] - 54
        body += f'<path d="M{x1} {y}H{x2}" stroke="{colour}" stroke-width="3" marker-end="url(#arrow-{key})"/>'
        body += _text((x1 + x2) / 2, y - 14, label, 13, colour)
    yb = 368
    body += (
        f'<path d="M110 {y + 128}V{yb}H170M650 {yb}H710V{y + 128}" stroke="{GREY}" stroke-width="2.5" '
        f'stroke-dasharray="7 6" fill="none" marker-end="url(#arrow-x)"/>'
        f'<rect x="170" y="{yb - 24}" width="480" height="48" rx="24" fill="{CARD}" stroke="{GREY}" '
        f'stroke-width="1.5"/>'
    )
    body += _icon("lock", 204, yb, TEXT, 1.0)
    body += _text(
        232,
        yb + 6,
        "You use your stacks through Cloudflare, after an email login",
        14.5,
        TEXT,
        500,
        "start",
    )
    body += _text(410, yb + 46, "The server has no open ports.", 14, SUB)
    return _svg(
        820,
        430,
        "Nexus Stack in one picture",
        "You say what you want. GitHub builds it. Your server runs it.",
        "Nexus Stack in one picture: you, the Control Plane, GitHub Actions and your server",
        body,
    )


def lifecycle() -> str:
    """What survives a teardown?"""
    body = (
        f'<rect x="60" y="130" width="250" height="120" rx="14" fill="{CARD}" stroke="{GREEN}" stroke-width="3"/>'
        + _text(185, 178, "Running", 22, GREEN, 700)
        + _text(185, 206, ["server up, stacks reachable,", "billed by the hour"], 15, SUB)
        + f'<rect x="510" y="130" width="250" height="120" rx="14" fill="{CARD}" stroke="{GREY}" '
        f'stroke-width="3" stroke-dasharray="8 6"/>'
        + _text(635, 178, "Torn down", 22, TEXT, 700)
        + _text(635, 206, ["no server, no cost;", "what is kept: see below"], 15, SUB)
        + f'<path d="M318 165H502" stroke="{GREY}" stroke-width="3" marker-end="url(#arrow-x)"/>'
        + _text(410, 152, "Teardown", 16, TEXT, 600)
        + _text(410, 186, "by hand or on a schedule", 13.5, SUB)
        + f'<path d="M502 222H318" stroke="{GREEN}" stroke-width="3" marker-end="url(#arrow-g)"/>'
        + _text(410, 244, "Spin up", 16, GREEN, 600)
        + _text(36, 312, "What comes back depends on the mode you choose", 17, TEXT, 700, "start")
    )
    modes = (
        (
            36,
            BLUE,
            "Rebuild",
            ["A fresh server. Data is restored from", "backup for the stacks the backup covers."],
        ),
        (420, GREEN, "Snapshot", ["The whole disk is restored.", "Every stack keeps its data."]),
    )
    for x, colour, name, lines in modes:
        body += (
            f'<rect x="{x}" y="330" width="364" height="104" rx="12" fill="{CARD}"/>'
            f'<rect x="{x}" y="330" width="6" height="104" rx="3" fill="{colour}"/>'
            + _text(x + 24, 362, name, 18, colour, 700, "start")
            + _text(x + 24, 388, lines, 14.5, SUB, 400, "start")
        )
    return _svg(
        820,
        470,
        "The server is disposable, the data is not",
        "A teardown deletes the machine. A spin-up builds a new one.",
        "Lifecycle: running, teardown, torn down, spin up, and the two modes rebuild and snapshot",
        body,
    )


def request_path() -> str:
    """Why is no port open?"""
    y, y2 = 230, 378
    body = (
        f'<rect x="520" y="110" width="270" height="326" rx="16" fill="none" stroke="{GREEN}" stroke-width="2.5"/>'
        + _text(655, 140, "Your server", 17, GREEN, 700)
        + _text(655, 162, "0 open ports by default", 14, SUB)
        + f'<circle cx="80" cy="{y}" r="36" fill="{CARD}" stroke="{GREY}" stroke-width="3"/>'
        + _icon("user", 80, y, GREY, 1.4)
        + _text(80, y + 62, "You", 17, TEXT, 700)
        + _text(80, y + 84, "in the browser", 14, SUB)
        + f'<rect x="180" y="{y - 44}" width="210" height="88" rx="14" fill="{CARD}" stroke="{BLUE}" stroke-width="3"/>'
        + _text(285, y - 8, "Cloudflare", 19, BLUE, 700)
        + _text(285, y + 18, "asks for an email code", 14.5, SUB)
        + f'<rect x="570" y="{y - 36}" width="170" height="72" rx="12" fill="{CARD}" stroke="{GREEN}" stroke-width="3"/>'
        + _text(655, y - 2, "Your stack", 18, TEXT, 700)
        + _text(655, y + 20, "Kestra, Grafana, …", 14, SUB)
        + f'<path d="M122 {y}H172" stroke="{BLUE}" stroke-width="3" marker-end="url(#arrow-b)"/>'
        + f'<path d="M562 {y}H398" stroke="{GREEN}" stroke-width="3" marker-end="url(#arrow-g)"/>'
        + _text(456, y - 32, ["tunnel, opened", "from the inside"], 13, GREEN)
        + _icon("database", 80, y2, AMBER, 1.4)
        + _text(126, y2 - 4, ["A database or", "Kafka client"], 14.5, TEXT, 500, "start", 1.38)
        + f'<path d="M250 {y2}H562" stroke="{AMBER}" stroke-width="2.5" stroke-dasharray="7 6" '
        f'marker-end="url(#arrow-o)"/>'
        + f'<rect x="570" y="{y2 - 26}" width="170" height="52" rx="10" fill="{CARD}" stroke="{AMBER}" '
        f'stroke-width="2.5" stroke-dasharray="7 6"/>'
        + _text(655, y2 + 6, "one port you opened", 14.5, AMBER, 600)
        + _text(382, y2 - 14, "only after you open it on the Firewall page", 12.5, AMBER)
        + _text(382, y2 + 28, "closed again at every teardown", 12.5, SUB)
    )
    return _svg(
        820,
        470,
        "How a request reaches a stack",
        "The server never listens on the internet. It calls out to Cloudflare instead.",
        "Request path: browser, Cloudflare email login, a tunnel opened from inside the server, "
        "your stack; and one optional port that you open yourself",
        body,
    )


def three_planes() -> str:
    """Which parts are there, and where does state live?"""
    planes = (
        (
            36,
            BLUE,
            "Control plane",
            "Cloudflare",
            [
                "The Control Plane website.",
                "Stores which stacks are on,",
                "your settings and firewall rules.",
            ],
        ),
        (
            292,
            AMBER,
            "Execution plane",
            "GitHub Actions",
            [
                "Runs every change.",
                "OpenTofu creates the server,",
                "nexus_deploy starts the stacks.",
            ],
        ),
        (
            548,
            GREEN,
            "Data plane",
            "Hetzner Cloud",
            ["One server with Docker.", "Your stacks and your data", "live here while it runs."],
        ),
    )
    body = ""
    for x, colour, name, where, lines in planes:
        body += (
            f'<rect x="{x}" y="112" width="236" height="204" rx="14" fill="{CARD}"/>'
            f'<rect x="{x}" y="112" width="236" height="8" rx="4" fill="{colour}"/>'
            + _text(x + 20, 156, name, 20, colour, 700, "start")
            + _text(x + 20, 180, where, 14.5, TEXT, 600, "start")
            + _text(x + 20, 216, lines, 14.5, SUB, 400, "start", 1.45)
        )
    body += (
        f'<path d="M272 214H288" stroke="{AMBER}" stroke-width="3" marker-end="url(#arrow-o)"/>'
        f'<path d="M528 214H544" stroke="{GREEN}" stroke-width="3" marker-end="url(#arrow-g)"/>'
        f'<rect x="36" y="346" width="748" height="92" rx="14" fill="none" stroke="{GREY}" stroke-width="2" '
        f'stroke-dasharray="8 6"/>'
        + _text(56, 380, "What outlives the server", 17, TEXT, 700, "start")
        + _text(
            56,
            408,
            "OpenTofu state and data backups in Cloudflare R2 · optional disk snapshot at Hetzner",
            14.5,
            SUB,
            400,
            "start",
        )
    )
    return _svg(
        820,
        470,
        "Three planes that never merge",
        "Nothing you click touches the server directly.",
        "Three planes: the control plane at Cloudflare, the execution plane in GitHub Actions, "
        "the data plane at Hetzner; state that outlives the server sits in R2 and in a disk snapshot",
        body,
    )


def snapshot_teardown_order() -> str:
    """Why does the snapshot teardown do things in this order?"""
    steps = (
        (
            BLUE,
            "Back up data to R2",
            "First, because it needs the containers still running.",
            "If it fails, the run stops and nothing is destroyed.",
        ),
        (
            GREEN,
            "Power off the server",
            "A disk is only consistent when nothing writes to it.",
            "The run waits until the server reports off.",
        ),
        (
            GREEN,
            "Take the disk snapshot",
            "Waits until the image is available, not just started.",
            "It is labelled with the credential epoch.",
        ),
        (
            BLUE,
            "Record it in the Control Plane",
            "A copy for the Control Plane to show.",
            "The labels at Hetzner stay the source of truth.",
        ),
        (
            AMBER,
            "Destroy only the server",
            "Only now. Passwords, tunnel, DNS and login rules stay.",
            "That is what keeps the snapshot restorable.",
        ),
        (
            GREEN,
            "Delete older snapshots",
            "Last, and only after a new snapshot exists.",
            "Pruning first could leave nothing to restore from.",
        ),
    )
    top, pitch, height = 112, 78, 58
    body = ""
    for i, (colour, name, why, detail) in enumerate(steps):
        y = top + i * pitch
        body += (
            f'<rect x="36" y="{y}" width="300" height="{height}" rx="12" fill="{CARD}" '
            f'stroke="{colour}" stroke-width="2.5"/>'
            + _text(186, y + 35, name, 16, TEXT, 700)
            + _text(366, y + 25, why, 14.5, TEXT, 500, "start")
            + _text(366, y + 46, detail, 13.5, SUB, 400, "start")
        )
        if i:
            body += (
                f'<path d="M186 {y - pitch + height + 2}V{y - 3}" stroke="{GREY}" stroke-width="2.5" '
                f'marker-end="url(#arrow-x)"/>'
            )
    yb = top + len(steps) * pitch + 4
    body += (
        f'<rect x="36" y="{yb}" width="748" height="92" rx="14" fill="none" stroke="{GREY}" '
        f'stroke-width="2" stroke-dasharray="8 6"/>'
        + _text(56, yb + 28, "If the disk snapshot fails", 16, TEXT, 700, "start")
        + _text(
            56,
            yb + 50,
            [
                "The server is still destroyed: the R2 backup already ran, and the next spin-up builds fresh.",
                "With strict_snapshot the run stops before the destroy and the server is kept.",
            ],
            13.5,
            SUB,
            400,
            "start",
            1.45,
        )
    )
    return _svg(
        820,
        yb + 122,
        "Snapshot teardown: the order is the safety",
        "Each step sits where it does because of what the next one would destroy.",
        "Snapshot teardown order: back up data to R2, power off, take the disk snapshot, record "
        "it in the Control Plane, destroy only the server, delete older snapshots",
        body,
    )


def credential_epoch() -> str:
    """Why is an old snapshot refused after a rebuild teardown?"""
    body = (
        f'<rect x="36" y="106" width="748" height="74" rx="14" fill="{CARD}"/>'
        f'<rect x="36" y="106" width="6" height="74" rx="3" fill="{BLUE}"/>'
        + _text(60, 136, "The credential epoch", 18, BLUE, 700, "start")
        + _text(
            60,
            160,
            "A fingerprint of generated passwords. Each snapshot is labelled with the one it was taken under.",
            14,
            SUB,
            400,
            "start",
        )
    )
    lanes = (
        (
            36,
            GREEN,
            "g",
            "Snapshot teardown",
            (
                "destroys only the server",
                "passwords stay, so the fingerprint stays",
                "the snapshot matches and is restored",
            ),
        ),
        (
            420,
            AMBER,
            "o",
            "Rebuild teardown",
            (
                "destroys most passwords too",
                "the next spin-up makes new ones",
                "older snapshots no longer match: refused",
            ),
        ),
    )
    for x, colour, key, name, rows in lanes:
        body += (
            f'<rect x="{x}" y="204" width="364" height="246" rx="14" fill="none" stroke="{colour}" '
            f'stroke-width="2.5"/>' + _text(x + 182, 236, name, 18, colour, 700)
        )
        for i, row in enumerate(rows):
            y = 256 + i * 64
            body += (
                f'<rect x="{x + 20}" y="{y}" width="324" height="44" rx="10" fill="{CARD}"/>'
                + _text(x + 182, y + 28, row, 14.5, TEXT, 500)
            )
            if i:
                body += (
                    f'<path d="M{x + 182} {y - 18}V{y - 3}" stroke="{colour}" stroke-width="2.5" '
                    f'marker-end="url(#arrow-{key})"/>'
                )
    body += (
        f'<rect x="36" y="474" width="748" height="98" rx="14" fill="none" stroke="{GREY}" '
        f'stroke-width="2" stroke-dasharray="8 6"/>'
        + _text(56, 504, "The refusal is the guard working", 16, TEXT, 700, "start")
        + _text(
            56,
            527,
            [
                "The old disk holds databases and accounts made with the old passwords. Restored, the stack",
                "would boot and log in nowhere. The spin-up builds a fresh server and restores from R2 instead.",
            ],
            13.5,
            SUB,
            400,
            "start",
            1.45,
        )
    )
    return _svg(
        820,
        600,
        "Why an old snapshot can be refused",
        "Never run the Rebuild teardown at a stack that lives on snapshots.",
        "Credential epoch: a snapshot teardown keeps the passwords and the snapshot stays "
        "restorable; a rebuild teardown regenerates them and older snapshots are refused",
        body,
    )


def snapshot_spin_up_decision() -> str:
    """What does the spin-up do when it cannot find out whether there is a snapshot?"""
    cards = (
        (
            36,
            GREEN,
            "g",
            "Yes",
            ["Restore the disk from", "the snapshot."],
            ["The R2 restore is off:", "the snapshot is newer."],
        ),
        (
            292,
            BLUE,
            "b",
            "Definitely not",
            ["No snapshot exists, or its", "credential epoch differs."],
            ["Build a fresh server and", "restore from the R2 backup."],
        ),
        (
            548,
            AMBER,
            "o",
            "Cannot tell",
            ["The snapshot lookup failed,", "or the state is unreachable."],
            ["Stop. Nothing is built", "until someone looks."],
        ),
    )
    body = (
        f'<rect x="100" y="104" width="620" height="46" rx="23" fill="{CARD}" stroke="{GREY}" '
        f'stroke-width="2"/>'
        + _text(410, 133, "Spin-up: is there a snapshot to restore?", 15.5, TEXT, 600)
    )
    for x, colour, key, name, found, action in cards:
        cx = x + 118
        body += (
            f'<path d="M{cx} 152V184" stroke="{colour}" stroke-width="2.5" marker-end="url(#arrow-{key})"/>'
            f'<rect x="{x}" y="188" width="236" height="190" rx="14" fill="{CARD}"/>'
            f'<rect x="{x}" y="188" width="236" height="8" rx="4" fill="{colour}"/>'
            + _text(x + 20, 230, name, 20, colour, 700, "start")
            + _text(x + 20, 262, found, 14, SUB, 400, "start", 1.45)
            + _text(x + 20, 320, action, 14.5, TEXT, 600, "start", 1.45)
        )
    body += _text(36, 422, "The same rule picks the workflow pair", 17, TEXT, 700, "start")
    pairs = (
        (
            36,
            BLUE,
            "No lifecycle_mode stored",
            ["A definite answer: the stack was never", "switched. The rebuild pair is used."],
        ),
        (
            420,
            AMBER,
            "Database unreadable, or the value unknown",
            ["Cannot tell which pair is right.", "Nothing is dispatched."],
        ),
    )
    for x, colour, name, lines in pairs:
        body += (
            f'<rect x="{x}" y="440" width="364" height="100" rx="12" fill="{CARD}"/>'
            f'<rect x="{x}" y="440" width="6" height="100" rx="3" fill="{colour}"/>'
            + _text(x + 24, 470, name, 15.5, colour, 700, "start")
            + _text(x + 24, 496, lines, 14, SUB, 400, "start", 1.45)
        )
    body += _text(
        410,
        574,
        "A guess after a failed lookup could put an older backup on top of a newer snapshot.",
        14,
        SUB,
    )
    return _svg(
        820,
        600,
        "Cannot tell is not the same as there is none",
        "A definite no falls back. An unknown stops.",
        "Snapshot spin-up decision: a usable snapshot is restored, a definite absence builds "
        "fresh from the R2 backup, and a failed lookup stops the run",
        body,
    )


DIAGRAMS: dict[str, Callable[[], str]] = {
    "nexus-stack-in-one-picture.svg": one_picture,
    "lifecycle.svg": lifecycle,
    "request-path.svg": request_path,
    "three-planes.svg": three_planes,
}


# The pictures for the snapshot-lifecycle guide. They live next to the guide,
# in docs/admin-guides/assets/, because a guide embeds `./assets/<name>` and
# the website sync copies each guide folder's own assets.
ADMIN_GUIDE_DIAGRAMS: dict[str, Callable[[], str]] = {
    "snapshot-teardown-order.svg": snapshot_teardown_order,
    "snapshot-credential-epoch.svg": credential_epoch,
    "snapshot-spin-up-decision.svg": snapshot_spin_up_decision,
}

# Folder, relative to the repository root, and the diagrams rendered into it.
FOLDERS: dict[str, dict[str, Callable[[], str]]] = {
    "docs/concepts/assets": DIAGRAMS,
    "docs/admin-guides/assets": ADMIN_GUIDE_DIAGRAMS,
}


def write(repo: Path) -> list[Path]:
    """Render every diagram into its folder and return the paths."""
    written = []
    for folder, diagrams in FOLDERS.items():
        target = repo / folder
        target.mkdir(parents=True, exist_ok=True)
        for name, render in diagrams.items():
            path = target / name
            path.write_text(render(), encoding="utf-8")
            written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover — maintenance entry point
    # uv run python -m nexus_deploy.doc_diagrams
    for _path in write(Path(__file__).resolve().parents[2]):
        print(_path)
