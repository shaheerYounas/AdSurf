from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.sqlite_init import initialize_sqlite_schema
from apps.api.app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def sqlite_database(monkeypatch, tmp_path):
    db_path = tmp_path / "adsurf.db"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    get_database_engine.cache_clear()
    initialize_sqlite_schema()
    yield
    get_database_engine.cache_clear()
    get_settings.cache_clear()


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "x-user-id": user_id,
        "x-test-workspaces": f"{workspace_id}:{role}",
    }


def test_custom_agent_routes_block_cross_workspace_object_access() -> None:
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    _ensure_workspace(workspace_a)
    _ensure_workspace(workspace_b)
    agent = _create_agent(workspace_a)

    get_from_other_workspace = client.get(
        f"/v1/workspaces/{workspace_b}/custom-agents/{agent['id']}",
        headers=auth_headers(workspace_b),
    )
    child_list_from_other_workspace = client.get(
        f"/v1/workspaces/{workspace_b}/custom-agents/{agent['id']}/tools",
        headers=auth_headers(workspace_b),
    )

    assert get_from_other_workspace.status_code == 404
    assert get_from_other_workspace.json()["error"]["code"] == "CUSTOM_AGENT_NOT_FOUND"
    assert child_list_from_other_workspace.status_code == 404
    assert child_list_from_other_workspace.json()["error"]["code"] == "CUSTOM_AGENT_NOT_FOUND"


def test_custom_agent_child_records_inherit_and_enforce_workspace() -> None:
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    _ensure_workspace(workspace_a)
    _ensure_workspace(workspace_b)
    agent = _create_agent(workspace_a)

    tool_response = client.post(
        f"/v1/workspaces/{workspace_a}/custom-agents/{agent['id']}/tools",
        headers=auth_headers(workspace_a),
        json={"agent_id": agent["id"], "tool_name": "web_search", "permission_level": "read"},
    )
    assert tool_response.status_code == 200
    tool = tool_response.json()["data"]
    assert tool["workspace_id"] == workspace_a

    blocked_update = client.patch(
        f"/v1/workspaces/{workspace_b}/custom-agents/{agent['id']}/tools/{tool['id']}",
        headers=auth_headers(workspace_b),
        json={"enabled": False},
    )
    assert blocked_update.status_code == 404
    assert blocked_update.json()["error"]["code"] == "CUSTOM_AGENT_NOT_FOUND"


def test_custom_agent_kb_link_requires_same_workspace() -> None:
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    _ensure_workspace(workspace_a)
    _ensure_workspace(workspace_b)
    agent = _create_agent(workspace_a)
    kb = _create_knowledge_base(workspace_b)

    response = client.post(
        f"/v1/workspaces/{workspace_a}/custom-agents/{agent['id']}/knowledge-bases/{kb['id']}",
        headers=auth_headers(workspace_a),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "KNOWLEDGE_BASE_NOT_FOUND"


def _create_agent(workspace_id: str) -> dict:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/custom-agents",
        headers=auth_headers(workspace_id),
        json={
            "workspace_id": workspace_id,
            "name": "QA Scoped Agent",
            "description": "Workspace isolation regression test",
            "role_instructions": "Stay inside the workspace.",
            "model_provider": "deepseek",
            "model_name": "deepseek-chat",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def _ensure_workspace(workspace_id: str) -> None:
    with get_database_engine().begin() as connection:
        connection.execute(
            text(
                """
                insert or ignore into workspaces (id, name, type, status, created_at, updated_at)
                values (:id, 'QA Workspace', 'seller', 'active', datetime('now'), datetime('now'))
                """
            ),
            {"id": workspace_id},
        )


def _create_knowledge_base(workspace_id: str) -> dict:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/knowledge-bases",
        headers=auth_headers(workspace_id),
        json={
            "workspace_id": workspace_id,
            "name": "QA Knowledge Base",
            "description": "Workspace isolation regression test",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]
