"""Tests for nexus_deploy.tfvars.

Pure-logic test surface. Two layers:

1. ``parse(path)`` — regex extraction of domain / admin_email /
   user_email from a synthetic config.tfvars fixture.
2. ``derive_forgejo_identity(config)`` — admin-email collision
   fallback + first-comma-trim semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus_deploy.tfvars import (
    ForgejoIdentity,
    TfvarsConfig,
    TfvarsError,
    derive_forgejo_identity,
    parse,
)

# ---------------------------------------------------------------------------
# parse() — file I/O + regex extraction
# ---------------------------------------------------------------------------


def _write_tfvars(path: Path, content: str) -> Path:
    """Helper: write a config.tfvars fixture to a tmp_path."""
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_standard_form(tmp_path: Path) -> None:
    """The vanilla case: 3 single-line double-quoted assignments."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\n'
        'admin_email = "admin@example.com"\n'
        'user_email = "user@example.com"\n',
    )
    assert parse(fixture) == TfvarsConfig(
        domain="example.com",
        admin_email_raw="admin@example.com",
        user_email_raw="user@example.com",
    )


def test_parse_comma_separated_user_email(tmp_path: Path) -> None:
    """user_email may be a comma-list for the CF Access allow-list.
    parse() returns it RAW; the comma-split happens in derive()."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\n'
        'admin_email = "admin@example.com"\n'
        'user_email = "alice@example.com, bob@example.com"\n',
    )
    config = parse(fixture)
    assert config.user_email_raw == "alice@example.com, bob@example.com"


def test_parse_missing_admin_email(tmp_path: Path) -> None:
    """admin_email may be absent (self-provisioned tfvars often omit
    it). parse() returns an empty string; derive() applies the
    synthetic fallback."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nuser_email = "user@example.com"\n',
    )
    assert parse(fixture).admin_email_raw == ""


def test_parse_extra_keys_are_ignored(tmp_path: Path) -> None:
    """The regex only captures domain / admin_email / user_email.
    Other tfvars keys (cloudflare_api_token, hcloud_token, etc.) must
    NOT trip the parser into emitting unexpected fields."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\n'
        'cloudflare_api_token = "ABC123_secret_token"\n'
        'admin_email = "admin@example.com"\n'
        'hcloud_token = "secret_too"\n'
        'user_email = "user@example.com"\n',
    )
    config = parse(fixture)
    assert config.domain == "example.com"
    assert config.admin_email_raw == "admin@example.com"
    assert config.user_email_raw == "user@example.com"


def test_parse_whitespace_around_equals(tmp_path: Path) -> None:
    """The regex tolerates whitespace around ``=``: ``var = "x"``
    AND ``var="x"`` are both valid HCL."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain="example.com"\nadmin_email = "admin@example.com"\n',
    )
    config = parse(fixture)
    assert config.domain == "example.com"
    assert config.admin_email_raw == "admin@example.com"


def test_parse_trailing_hash_comment(tmp_path: Path) -> None:
    """PR #535 R2 #3: hand-edited tfvars with HCL line-comments after
    the closing quote must still parse. Legacy bash grep/sed handled
    these fine; the original strict regex silently dropped them."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com" # primary domain\n'
        'admin_email = "admin@example.com"  # ops contact\n'
        'user_email = "user@example.com"\n',
    )
    config = parse(fixture)
    assert config.domain == "example.com"
    assert config.admin_email_raw == "admin@example.com"
    assert config.user_email_raw == "user@example.com"


def test_parse_trailing_slash_comment(tmp_path: Path) -> None:
    """PR #535 R2 #3: HCL also accepts ``//`` line-comments."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com" // primary\nadmin_email = "a@example.com"\n',
    )
    assert parse(fixture).domain == "example.com"


def test_parse_whitespace_inside_value_preserved(tmp_path: Path) -> None:
    """Leading/trailing space inside the quoted value IS preserved by
    parse() — the trim happens in derive()."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\n'
        'admin_email = "  admin@example.com  "\n'
        'user_email = " user@example.com"\n',
    )
    config = parse(fixture)
    assert config.admin_email_raw == "  admin@example.com  "
    assert config.user_email_raw == " user@example.com"


def test_parse_unquoted_values_not_matched(tmp_path: Path) -> None:
    """The regex requires double-quoted values. An unquoted line
    silently doesn't match — that's fine for our project's
    convention but could surprise a future contributor. Test pins
    the behavior so a regex relaxation is a deliberate decision."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nadmin_email = unquoted\n',
    )
    config = parse(fixture)
    assert config.domain == "example.com"
    assert config.admin_email_raw == ""  # unquoted line didn't match


def test_parse_empty_file(tmp_path: Path) -> None:
    """Empty config.tfvars → all-empty TfvarsConfig (defaults). The
    pipeline's own gates (e.g. ``if not domain``) decide whether to
    abort."""
    fixture = _write_tfvars(tmp_path / "config.tfvars", "")
    assert parse(fixture) == TfvarsConfig()


def test_parse_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TfvarsError, match=r"config\.tfvars not found"):
        parse(tmp_path / "does-not-exist.tfvars")


def test_parse_wraps_unreadable_file_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """File is_file() True (passes the missing-file gate) but
    read_text raises OSError → TfvarsError carries the cause."""
    fixture = _write_tfvars(tmp_path / "config.tfvars", "")

    def _raise_oserror(_self: Path, **_kw: object) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)
    with pytest.raises(TfvarsError, match=r"could not read .* PermissionError"):
        parse(fixture)


# ---------------------------------------------------------------------------
# derive_forgejo_identity — admin/user collision fallback
# ---------------------------------------------------------------------------


def test_derive_no_collision(tfvars_no_collision: TfvarsConfig) -> None:
    """admin distinct from user → both used as-is."""
    identity = derive_forgejo_identity(tfvars_no_collision)
    assert identity == ForgejoIdentity(
        admin_email="admin@example.com",
        forgejo_user_email="user@example.com",
        forgejo_user_username="user",
        om_principal_domain="example.com",
    )


def test_derive_collision_falls_back_to_synthetic(
    tfvars_collision: TfvarsConfig,
) -> None:
    """admin == user → synthesise forgejo-admin@<domain>."""
    identity = derive_forgejo_identity(tfvars_collision)
    assert identity.admin_email == "forgejo-admin@example.com"
    assert identity.forgejo_user_email == "shared@example.com"
    assert identity.om_principal_domain == "example.com"


def test_derive_empty_admin_falls_back_to_synthetic(tmp_path: Path) -> None:
    """admin_email empty → synthesise. Same path as the collision
    case (the `if not admin OR admin == user` gate)."""
    config = TfvarsConfig(
        domain="example.com",
        admin_email_raw="",
        user_email_raw="user@example.com",
    )
    assert derive_forgejo_identity(config).admin_email == "forgejo-admin@example.com"


def test_derive_first_comma_entry_used(tmp_path: Path) -> None:
    """Multi-admin user_email list: only the first entry is used for
    the Forgejo user.email column (Forgejo rejects commas with 'unsupported
    character')."""
    config = TfvarsConfig(
        domain="example.com",
        admin_email_raw="admin@example.com",
        user_email_raw="first@example.com, second@example.com, third@example.com",
    )
    identity = derive_forgejo_identity(config)
    assert identity.forgejo_user_email == "first@example.com"
    assert identity.forgejo_user_username == "first"


def test_derive_trims_whitespace_from_emails(tmp_path: Path) -> None:
    """Self-provisioned tfvars commonly have leading spaces inside
    quoted values. Forgejo/Windmill/Wiki.js validators reject those, so
    derive() trims both halves before further processing."""
    config = TfvarsConfig(
        domain="example.com",
        admin_email_raw="   admin@example.com   ",
        user_email_raw=" user@example.com ",
    )
    identity = derive_forgejo_identity(config)
    assert identity.admin_email == "admin@example.com"
    assert identity.forgejo_user_email == "user@example.com"


def test_derive_username_is_local_part(tmp_path: Path) -> None:
    """forgejo_user_username = local part of email (text before @)."""
    config = TfvarsConfig(
        domain="example.com",
        admin_email_raw="admin@example.com",
        user_email_raw="alice.bob+tag@university.edu",
    )
    assert derive_forgejo_identity(config).forgejo_user_username == "alice.bob+tag"


def test_derive_om_principal_domain_extracted_from_admin(tmp_path: Path) -> None:
    """OM_PRINCIPAL_DOMAIN is the domain part of the (post-fallback)
    admin_email. With the synthetic fallback, that's the configured
    project domain."""
    config = TfvarsConfig(
        domain="my.subdomain.example.com",
        admin_email_raw="admin@my.subdomain.example.com",
        user_email_raw="user@my.subdomain.example.com",
    )
    identity = derive_forgejo_identity(config)
    # Collision → synthetic admin → OM domain = project domain
    assert identity.om_principal_domain == "my.subdomain.example.com"


def test_derive_no_user_email_skips_username(tmp_path: Path) -> None:
    """When user_email is empty, the orchestrator's user-create gate
    skips. derive() returns empty username — NOT the admin fallback
    (which would re-introduce the original collision bug)."""
    config = TfvarsConfig(
        domain="example.com",
        admin_email_raw="admin@example.com",
        user_email_raw="",
    )
    identity = derive_forgejo_identity(config)
    assert identity.forgejo_user_email == ""
    assert identity.forgejo_user_username == ""
    assert identity.admin_email == "admin@example.com"


def test_derive_collision_with_no_domain_returns_empty_admin(tmp_path: Path) -> None:
    """Defensive: if domain is empty AND we hit the collision branch,
    we can't synthesise forgejo-admin@<empty> meaningfully — return an
    empty admin_email and let the pipeline's own gates abort. (The
    pipeline rejects empty domain BEFORE this function runs, so this
    branch is a defence-in-depth safety net.)"""
    config = TfvarsConfig(
        domain="",
        admin_email_raw="shared@somewhere.com",
        user_email_raw="shared@somewhere.com",
    )
    assert derive_forgejo_identity(config).admin_email == ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tfvars_no_collision() -> TfvarsConfig:
    return TfvarsConfig(
        domain="example.com",
        admin_email_raw="admin@example.com",
        user_email_raw="user@example.com",
    )


@pytest.fixture
def tfvars_collision() -> TfvarsConfig:
    return TfvarsConfig(
        domain="example.com",
        admin_email_raw="shared@example.com",
        user_email_raw="shared@example.com",
    )


# ---------------------------------------------------------------------------
# Frozen-dataclass invariants
# ---------------------------------------------------------------------------


def test_tfvars_config_frozen() -> None:
    from dataclasses import FrozenInstanceError

    config = TfvarsConfig(domain="x", admin_email_raw="y", user_email_raw="z")
    with pytest.raises(FrozenInstanceError):
        config.domain = "other"  # type: ignore[misc]


def test_forgejo_identity_frozen() -> None:
    from dataclasses import FrozenInstanceError

    identity = ForgejoIdentity(
        admin_email="a", forgejo_user_email="b", forgejo_user_username="c", om_principal_domain="d"
    )
    with pytest.raises(FrozenInstanceError):
        identity.admin_email = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# subdomain_separator parsing (Issue #540)
# ---------------------------------------------------------------------------


def test_parse_subdomain_separator_default_is_dot(tmp_path: Path) -> None:
    """Missing key in config.tfvars → default to '.' (single-tenant
    standard). Backward-compatible with every existing operator
    config that pre-dates the feature."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\n',
    )
    assert parse(fixture).subdomain_separator == "."


def test_parse_subdomain_separator_dash(tmp_path: Path) -> None:
    """Multi-tenant fork: separator='-' parsed verbatim."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "user1.example.com"\nsubdomain_separator = "-"\n',
    )
    config = parse(fixture)
    assert config.domain == "user1.example.com"
    assert config.subdomain_separator == "-"


def test_parse_subdomain_separator_empty_falls_back_to_dot(tmp_path: Path) -> None:
    """Explicit empty string in tfvars (``subdomain_separator = \"\"``)
    falls back to '.' — an empty separator would compose
    ``kestrauser1.example.com`` which doesn't match any provisioned
    DNS shape."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nsubdomain_separator = ""\n',
    )
    assert parse(fixture).subdomain_separator == "."


def test_parse_subdomain_separator_whitespace_only_falls_back_to_dot(
    tmp_path: Path,
) -> None:
    """``subdomain_separator = \"  \"`` — whitespace-only also falls
    back to '.' since strip() reduces it to empty."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nsubdomain_separator = "  "\n',
    )
    assert parse(fixture).subdomain_separator == "."


def test_parse_subdomain_separator_with_inline_comment(tmp_path: Path) -> None:
    """Trailing HCL comment after the value still parses (matches the
    existing comment-handling for domain / admin_email)."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nsubdomain_separator = "-" # flat-subdomain tenant\n',
    )
    assert parse(fixture).subdomain_separator == "-"


def test_parse_subdomain_separator_invalid_value_raises(tmp_path: Path) -> None:
    """PR #541 R1 #1: separator must be '.' or '-' (matching the Tofu
    IaC validation). Any other value raises TfvarsError so the
    operator sees a clear failure instead of malformed service URLs."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nsubdomain_separator = "x"\n',
    )
    with pytest.raises(TfvarsError, match=r"invalid subdomain_separator 'x'"):
        parse(fixture)


def test_parse_subdomain_separator_underscore_rejected(tmp_path: Path) -> None:
    """Underscore is a tempting choice (looks separator-like) but
    isn't valid DNS in this layer."""
    fixture = _write_tfvars(
        tmp_path / "config.tfvars",
        'domain = "example.com"\nsubdomain_separator = "_"\n',
    )
    with pytest.raises(TfvarsError, match=r"must be '\.'.*'-'"):
        parse(fixture)
