from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app


client = TestClient(app)


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "x-user-id": user_id,
        "x-test-workspaces": f"{workspace_id}:{role}",
    }


def test_health_endpoint_uses_standard_success_envelope() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["meta"] == {}


def test_product_profile_crud_routes_are_workspace_scoped() -> None:
    workspace_id = str(uuid4())
    create_response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={
            "product_name": "Vinyl Tool",
            "asin": "B0ABC12345",
            "sku": "VINYL-1",
            "target_acos": "0.45",
            "default_budget": "12.50",
            "default_bid": "1.25",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()["data"]
    assert created["workspace_id"] == workspace_id
    assert created["marketplace"] == "US"
    assert created["currency"] == "USD"

    list_response = client.get(f"/v1/workspaces/{workspace_id}/products", headers=auth_headers(workspace_id))
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    get_response = client.get(
        f"/v1/workspaces/{workspace_id}/products/{created['id']}",
        headers=auth_headers(workspace_id),
    )
    assert get_response.status_code == 200
    assert get_response.json()["data"]["product_name"] == "Vinyl Tool"

    patch_response = client.patch(
        f"/v1/workspaces/{workspace_id}/products/{created['id']}",
        headers=auth_headers(workspace_id),
        json={"product_name": "Vinyl Tool Updated", "default_bid": "1.50"},
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["data"]
    assert updated["product_name"] == "Vinyl Tool Updated"
    assert updated["default_bid"] == "1.5000"


def test_dashboard_summary_endpoint_returns_single_workspace_payload() -> None:
    workspace_id = str(uuid4())
    create_response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": "Dashboard Product"},
    )
    assert create_response.status_code == 201

    response = client.get(f"/v1/workspaces/{workspace_id}/dashboard-summary", headers=auth_headers(workspace_id, role="viewer"))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["product_count"] == 1
    assert data["upload_count"] == 0
    assert data["pending_recommendation_count"] == 0
    assert data["products"][0]["product_name"] == "Dashboard Product"


def test_product_profile_validation_error_uses_standard_error_envelope() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": "", "target_acos": "2"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_placeholder_auth_fails_closed_outside_local_and_test(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "staging")
    workspace_id = str(uuid4())

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": "Vinyl Tool"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHENTICATED"

    get_settings.cache_clear()


def test_missing_app_env_fails_closed_for_workspace_auth(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("APP_ENV", raising=False)
    workspace_id = str(uuid4())

    response = client.get(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "APP_ENV_NOT_CONFIGURED"

    get_settings.cache_clear()


def test_unknown_app_env_fails_closed_for_workspace_auth(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "qa")
    workspace_id = str(uuid4())

    response = client.get(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "APP_ENV_NOT_CONFIGURED"

    get_settings.cache_clear()


def test_staging_auth_fails_closed_when_supabase_jwt_is_not_configured(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    workspace_id = str(uuid4())

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers={"authorization": "Bearer local-placeholder-token"},
        json={"product_name": "Vinyl Tool"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"

    get_settings.cache_clear()


def test_production_auth_fails_closed_when_supabase_jwt_is_not_configured(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    workspace_id = str(uuid4())

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers={"authorization": "Bearer local-placeholder-token"},
        json={"product_name": "Vinyl Tool"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"

    get_settings.cache_clear()


def test_test_env_allows_local_header_auth(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "test")
    workspace_id = str(uuid4())

    response = client.get(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="viewer"),
    )

    assert response.status_code == 200

    get_settings.cache_clear()


def test_local_env_allows_local_header_auth(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "local")
    workspace_id = str(uuid4())

    response = client.get(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="viewer"),
    )

    assert response.status_code == 200

    get_settings.cache_clear()


def test_missing_auth_returns_401() -> None:
    workspace_id = str(uuid4())

    response = client.get(f"/v1/workspaces/{workspace_id}/products")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_missing_workspace_membership_returns_403() -> None:
    workspace_id = str(uuid4())
    other_workspace_id = str(uuid4())

    response = client.get(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(other_workspace_id),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


def test_invalid_workspace_role_returns_403() -> None:
    workspace_id = str(uuid4())

    response = client.get(
        f"/v1/workspaces/{workspace_id}/products",
        headers={"x-user-id": "00000000-0000-0000-0000-000000000001", "x-test-workspaces": f"{workspace_id}:not-a-role"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_WORKSPACE_ROLE"


def test_local_test_workspace_roles_are_scoped_per_workspace() -> None:
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    workspace_c = str(uuid4())
    headers = {
        "x-user-id": "00000000-0000-0000-0000-000000000001",
        "x-test-workspaces": f"{workspace_a}:analyst,{workspace_b}:viewer",
    }

    write_a = client.post(
        f"/v1/workspaces/{workspace_a}/products",
        headers=headers,
        json={"product_name": "Analyst Product"},
    )
    write_b = client.post(
        f"/v1/workspaces/{workspace_b}/products",
        headers=headers,
        json={"product_name": "Viewer Product"},
    )
    read_c = client.get(
        f"/v1/workspaces/{workspace_c}/products",
        headers=headers,
    )

    assert write_a.status_code == 201
    assert write_b.status_code == 403
    assert write_b.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"
    assert read_c.status_code == 403
    assert read_c.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


def test_product_write_role_permissions() -> None:
    allowed_roles = ["owner", "admin", "analyst"]
    blocked_roles = ["approver", "viewer"]

    for role in allowed_roles:
        workspace_id = str(uuid4())
        response = client.post(
            f"/v1/workspaces/{workspace_id}/products",
            headers=auth_headers(workspace_id, role=role),
            json={"product_name": f"Allowed {role}"},
        )
        assert response.status_code == 201

    for role in blocked_roles:
        workspace_id = str(uuid4())
        response = client.post(
            f"/v1/workspaces/{workspace_id}/products",
            headers=auth_headers(workspace_id, role=role),
            json={"product_name": f"Blocked {role}"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"


def test_product_update_role_permissions() -> None:
    workspace_id = str(uuid4())
    create_response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="owner"),
        json={"product_name": "Role Update Product"},
    )
    product_id = create_response.json()["data"]["id"]

    for role in ["owner", "admin", "analyst"]:
        response = client.patch(
            f"/v1/workspaces/{workspace_id}/products/{product_id}",
            headers=auth_headers(workspace_id, role=role),
            json={"product_name": f"Updated by {role}"},
        )
        assert response.status_code == 200

    for role in ["approver", "viewer"]:
        response = client.patch(
            f"/v1/workspaces/{workspace_id}/products/{product_id}",
            headers=auth_headers(workspace_id, role=role),
            json={"product_name": f"Blocked {role}"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"
