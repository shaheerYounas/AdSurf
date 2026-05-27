from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app
from apps.api.app.repositories.jobs import get_job_repository
from apps.api.app.schemas.jobs import JobStatus
from apps.api.app.services.storage import LocalFakeStorageService
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker

client = TestClient(app)


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {"x-user-id": user_id, "x-test-workspaces": f"{workspace_id}:{role}"}


def test_account_import_detects_and_groups_bulk_report(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": "Existing Shoe", "asin": "B0TESTASIN", "sku": "SHOE-1"},
    )
    assert product.status_code == 201

    content = (
        "ASIN,SKU,Product,Campaign Name,Ad Group Name,Targeting,Customer Search Term,Impressions,Clicks,Spend,7 Day Total Sales,7 Day Total Orders\n"
        "B0TESTASIN,SHOE-1,Existing Shoe,Campaign A,Group A,running shoes,blue running shoes,100,12,24.50,80,2\n"
        "B0NEWASIN1,NEW-1,New Hat,Campaign B,Group B,sun hat,wide brim hat,50,10,15,0,0\n"
    ).encode()
    init = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": "account-report.csv",
            "mime_type": "text/csv",
            "file_size_bytes": len(content),
            "source_type": "account_bulk_report",
        },
    )
    assert init.status_code == 201
    upload = init.json()["data"]
    assert "/account-imports/uploads/" in upload["storage_path"]
    LocalFakeStorageService(root=str(tmp_path)).write_upload_object(storage_path=upload["storage_path"], content=content)
    confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert confirm.status_code == 200
    UploadProcessingWorker().process_one()

    detection = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/report-detection", headers=auth_headers(workspace_id))
    created = client.post(
        f"/v1/workspaces/{workspace_id}/account-imports",
        headers=auth_headers(workspace_id),
        json={"upload_id": upload["upload_id"]},
    )

    assert detection.status_code == 200
    assert detection.json()["data"]["detected_report_type"] == "sponsored_products_search_term_report"
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["import_record"]["status"] == "needs_mapping"
    assert data["detection"]["product_identifiers_available"] == ["asin", "sku", "product_name"]
    assert any(entity["entity_type"] == "account" and entity["metrics_json"]["clicks"] == 22 for entity in data["entities"])
    assert any(entity["entity_type"] == "search_term" and entity["customer_search_term"] == "blue running shoes" for entity in data["entities"])
    assert len(data["product_mapping_suggestions"]) == 1
    assert data["product_mapping_suggestions"][0]["asin"] == "B0NEWASIN1"


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    for workspace_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=workspace_id, job_id=job_id, status=JobStatus.CANCELLED)
