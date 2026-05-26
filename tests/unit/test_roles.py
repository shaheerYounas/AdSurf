from pathlib import Path

from apps.api.app.core.auth import CANONICAL_WORKSPACE_ROLES


EXPECTED_ROLES = ("owner", "admin", "analyst", "approver", "viewer")


def test_python_role_enum_matches_canonical_roles() -> None:
    assert CANONICAL_WORKSPACE_ROLES == EXPECTED_ROLES


def test_typescript_role_constants_match_canonical_roles() -> None:
    role_source = Path("packages/types/src/roles.ts").read_text(encoding="utf-8")

    for role in EXPECTED_ROLES:
        assert f'"{role}"' in role_source

    assert ("strate" + "gist") not in role_source
