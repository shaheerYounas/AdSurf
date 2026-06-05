from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.sqlite_init import initialize_sqlite_schema
from apps.api.app.main import app


client = TestClient(app)

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000001"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def auth_headers(role: str = "owner") -> dict:
    return {
        "x-user-id": USER_ID,
        "x-test-workspaces": f"{WORKSPACE_ID}:{role}",
    }


@pytest.fixture(autouse=True)
def sqlite_db(monkeypatch, tmp_path):
    db_path = tmp_path / "adsurf.db"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    get_database_engine.cache_clear()
    initialize_sqlite_schema()
    yield
    get_database_engine.cache_clear()
    get_settings.cache_clear()


def test_bulk_product_import_persists_preview_in_sqlite(monkeypatch, tmp_path) -> None:
    csv_content = (
        b"Product Name,ASIN,SKU,Target ACOS,Marketplace,Currency\n"
        b"Sample Product,B0TEST1234,SKU-1,30,US,USD\n"
    )

    response = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/products/bulk-import",
        headers=auth_headers(),
        files={"file": ("products.csv", csv_content, "text/csv")},
        data={"conflict_strategy": "skip_existing", "workspace_default_acos": "30"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "ready_for_review"
    assert data["total_rows"] == 1
    assert data["valid_rows"] == 1
    assert data["detected_columns"]["Product Name"] == "product_name"

    with get_database_engine().connect() as connection:
        persisted = connection.execute(
            text(
                """
                select original_filename, total_rows, valid_rows
                from bulk_product_imports
                where id = :id and workspace_id = :workspace_id
                """
            ),
            {"id": data["import_id"], "workspace_id": WORKSPACE_ID},
        ).mappings().one()
        row_count = connection.execute(
            text("select count(*) from bulk_product_import_rows where import_id = :id"),
            {"id": data["import_id"]},
        ).scalar_one()

    assert persisted["original_filename"] == "products.csv"
    assert persisted["total_rows"] == 1
    assert persisted["valid_rows"] == 1
    assert row_count == 1


def test_clean_csv_preview_then_commit_creates_only_after_confirmation() -> None:
    upload = _upload_fixture("bulk-products-valid.csv")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["total_rows"] == 3
    assert summary["valid_rows"] == 3
    assert summary["rows_to_create"] == 3
    assert _product_count() == 0

    commit = _commit(summary["import_id"])

    assert commit.status_code == 200
    result = commit.json()["data"]
    assert result["created_count"] == 3
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 0
    assert _product_count() == 3


def test_clean_xlsx_preview_then_commit_creates_products() -> None:
    upload = _upload_fixture("bulk-products-valid.xlsx")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["total_rows"] == 2
    assert summary["valid_rows"] == 2

    commit = _commit(summary["import_id"])

    assert commit.status_code == 200
    assert commit.json()["data"]["created_count"] == 2


def test_alternative_headers_map_correctly() -> None:
    upload = _upload_fixture("bulk-products-alt-headers.csv")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["detected_columns"]["Product Title"] == "product_name"
    assert summary["detected_columns"]["Advertised Product ASIN"] == "asin"
    assert summary["detected_columns"]["Merchant SKU"] == "sku"
    assert summary["detected_columns"]["Target aCoS %"] == "target_acos"
    assert summary["valid_rows"] == 2


def test_missing_target_acos_uses_user_default() -> None:
    upload = _upload_fixture("bulk-products-missing-acos.csv", workspace_default_acos="25")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["valid_rows"] == 2
    _commit(summary["import_id"])

    assert {product["target_acos"] for product in _products()} == {"0.2500"}


def test_file_target_acos_wins_over_user_default() -> None:
    upload = _upload_bytes(
        "products.csv",
        b"Product Name,ASIN,SKU,Target ACOS\nFile Wins,B0WIN12345,WIN-1,35\n",
        workspace_default_acos="25",
    )

    assert upload.status_code == 201
    summary = upload.json()["data"]
    _commit(summary["import_id"])

    assert _products()[0]["target_acos"] == "0.3500"


def test_duplicate_asins_in_same_file_are_detected_and_blocked() -> None:
    upload = _upload_fixture("bulk-products-duplicates.csv")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["duplicate_in_file_rows"] == 2
    assert summary["rows_needing_review"] == 2

    commit = _commit(summary["import_id"])

    assert commit.status_code == 200
    assert commit.json()["data"]["created_count"] == 1
    assert commit.json()["data"]["skipped_count"] == 2


def test_existing_products_skip_policy_skips_conflicts() -> None:
    _create_product(product_name="Existing Garlic Press", asin="B0SKIP1234", sku="SKIP-1")

    upload = _upload_fixture("bulk-products-existing-products.csv", conflict_strategy="skip_existing")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["already_exists_rows"] == 1
    assert summary["rows_to_create"] == 1
    assert summary["rows_to_skip"] == 1

    commit = _commit(summary["import_id"], conflict_strategy="skip_existing")

    assert commit.status_code == 200
    assert commit.json()["data"]["created_count"] == 1
    assert commit.json()["data"]["skipped_count"] == 1
    assert _product_count() == 2


def test_existing_products_update_policy_updates_in_place() -> None:
    existing = _create_product(product_name="Old Garlic Press", asin="B0SKIP1234", sku="SKIP-1")

    upload = _upload_fixture("bulk-products-existing-products.csv", conflict_strategy="update_existing")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["already_exists_rows"] == 0
    assert summary["rows_to_update"] == 1
    assert summary["rows_to_create"] == 1

    commit = _commit(summary["import_id"], conflict_strategy="update_existing")

    assert commit.status_code == 200
    result = commit.json()["data"]
    assert result["updated_count"] == 1
    assert result["created_count"] == 1
    products = _products()
    updated = next(product for product in products if product["id"] == existing["id"])
    assert updated["product_name"] == "Updated Garlic Press"
    assert updated["target_acos"] == "0.2800"
    assert _product_count() == 2


def test_invalid_rows_are_not_created() -> None:
    upload = _upload_fixture("bulk-products-invalid-rows.csv")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["total_rows"] == 5
    assert summary["valid_rows"] == 1
    assert summary["invalid_rows"] == 4

    commit = _commit(summary["import_id"])

    assert commit.status_code == 200
    assert commit.json()["data"]["created_count"] == 1
    assert commit.json()["data"]["skipped_count"] == 4
    assert _product_count() == 1


def test_confirming_same_import_twice_does_not_duplicate_products() -> None:
    upload = _upload_fixture("bulk-products-valid.csv")
    import_id = upload.json()["data"]["import_id"]

    first = _commit(import_id)
    second = _commit(import_id)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVALID_IMPORT_STATUS"
    assert _product_count() == 3


def test_accepts_more_than_500_rows_without_creating_products_before_confirm() -> None:
    upload = _upload_fixture("bulk-products-over-500-rows.csv")

    assert upload.status_code == 201
    summary = upload.json()["data"]
    assert summary["total_rows"] == 501
    assert summary["valid_rows"] == 501
    assert summary["rows_to_create"] == 501
    assert _product_count() == 0


def test_rejects_invalid_type_malformed_csv_and_blank_xlsx() -> None:
    invalid_type = _upload_bytes("products.txt", b"Product Name\nWidget\n")
    malformed = _upload_fixture("bulk-products-malformed.csv")
    blank_xlsx = _upload_fixture("bulk-products-empty.xlsx")

    assert invalid_type.status_code == 400
    assert invalid_type.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "MALFORMED_CSV"
    assert blank_xlsx.status_code == 422
    assert blank_xlsx.json()["error"]["code"] == "EMPTY_WORKBOOK"


def test_summary_counts_match_backend_commit_result() -> None:
    _create_product(product_name="Existing Garlic Press", asin="B0SKIP1234", sku="SKIP-1")
    upload = _upload_fixture("bulk-products-existing-products.csv", conflict_strategy="skip_existing")
    summary = upload.json()["data"]

    commit = _commit(summary["import_id"], conflict_strategy="skip_existing")
    result = commit.json()["data"]

    assert result["created_count"] == summary["rows_to_create"]
    assert result["skipped_count"] == summary["rows_to_skip"]
    assert result["failed_count"] == 0


def _upload_fixture(
    fixture_name: str,
    *,
    conflict_strategy: str = "skip_existing",
    workspace_default_acos: str | None = None,
):
    path = FIXTURES / fixture_name
    return _upload_bytes(
        fixture_name,
        path.read_bytes(),
        conflict_strategy=conflict_strategy,
        workspace_default_acos=workspace_default_acos,
    )


def _upload_bytes(
    filename: str,
    content: bytes,
    *,
    conflict_strategy: str = "skip_existing",
    workspace_default_acos: str | None = None,
):
    data = {"conflict_strategy": conflict_strategy}
    if workspace_default_acos is not None:
        data["workspace_default_acos"] = workspace_default_acos
    return client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/products/bulk-import",
        headers=auth_headers(),
        files={"file": (filename, content, _mime_type(filename))},
        data=data,
    )


def _commit(import_id: str, *, conflict_strategy: str = "skip_existing"):
    return client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/products/bulk-import/{import_id}/commit",
        headers={**auth_headers(), "Content-Type": "application/json"},
        json={"conflict_strategy": conflict_strategy},
    )


def _create_product(*, product_name: str, asin: str, sku: str) -> dict:
    response = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/products",
        headers=auth_headers(),
        json={
            "product_name": product_name,
            "asin": asin,
            "sku": sku,
            "marketplace": "US",
            "currency": "USD",
            "target_acos": "0.3000",
            "default_budget": "20.0000",
            "default_bid": "1.0000",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def _product_count() -> int:
    with get_database_engine().connect() as connection:
        return connection.execute(text("select count(*) from product_profiles where workspace_id = :workspace_id"), {"workspace_id": WORKSPACE_ID}).scalar_one()


def _products() -> list[dict]:
    response = client.get(f"/v1/workspaces/{WORKSPACE_ID}/products", headers=auth_headers())
    assert response.status_code == 200
    return response.json()["data"]


def _mime_type(filename: str) -> str:
    if filename.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if filename.endswith(".csv"):
        return "text/csv"
    return "text/plain"
