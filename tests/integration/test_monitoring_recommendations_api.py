from uuid import UUID, uuid4

from apps.api.app.repositories.audit_logs import get_audit_log_repository
from apps.api.app.schemas.jobs import JobStatus
from apps.api.app.services.monitoring_worker import MonitoringWorker
from apps.api.app.services.storage import LocalFakeStorageService
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker

from tests.integration.test_keyword_scoring_api import auth_headers, client
from apps.api.app.core.config import get_settings
from apps.api.app.repositories.jobs import get_job_repository


def test_monitoring_import_creates_recommendations_and_agent_summary(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)

    import_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    assert import_response.status_code == 200
    import_body = import_response.json()["data"]

    result = MonitoringWorker().process_one()
    assert result.processed is True
    assert result.import_record.status == "succeeded"

    recommendations_response = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id))
    recommendations = recommendations_response.json()["data"]
    types = {recommendation["recommendation_type"] for recommendation in recommendations}

    assert recommendations_response.status_code == 200
    assert import_body["import_record"]["status"] == "queued"
    assert {"pause_review", "negative_keyword_review", "decrease_bid", "watch_lock", "increase_bid"}.issubset(types)
    assert all(recommendation["status"] == "pending_approval" for recommendation in recommendations)
    assert all(recommendation["explanation_json"]["approval_required"] is True for recommendation in recommendations)

    monitoring = client.get(f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring", headers=auth_headers(workspace_id))
    assert monitoring.status_code == 200
    assert monitoring.json()["data"]["agent_summary"]["stakeholder_note"].endswith("has been executed.")

    audit_repository = get_audit_log_repository()
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="monitoring_import.queued", object_id=UUID(import_body["import_record"]["id"])) == 1


def test_recommendation_approval_and_rejection_require_notes_and_scope(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    recommendation = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"][0]

    missing_note = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{recommendation['id']}/approve",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"note": ""},
    )
    cross_workspace = client.get(f"/v1/workspaces/{uuid4()}/recommendations/{recommendation['id']}", headers=auth_headers(str(uuid4())))
    viewer_decision = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{recommendation['id']}/approve",
        headers=auth_headers(workspace_id, role="viewer"),
        json={"note": "Viewer should not be able to approve"},
    )
    approved = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{recommendation['id']}/approve",
        headers=auth_headers(workspace_id, role="approver"),
        json={"note": "Approved for manual Amazon console review"},
    )
    second_decision = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{recommendation['id']}/reject",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"note": "Changing my mind"},
    )

    assert missing_note.status_code == 422
    assert cross_workspace.status_code in {403, 404}
    assert viewer_decision.status_code == 403
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved"
    assert approved.json()["data"]["proposed_action_json"]["requires_human_approval"] is True
    assert second_decision.status_code == 409


def _processed_sp_report_upload(monkeypatch, tmp_path) -> tuple[str, str, str]:
    storage_root = tmp_path / "s"
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    content = _sp_report_csv().encode("utf-8")
    upload = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": "sp-search-term.csv",
            "mime_type": "text/csv",
            "file_size_bytes": len(content),
            "source_type": "amazon_ads_sp_search_term_report",
        },
    ).json()["data"]
    LocalFakeStorageService(root=str(storage_root)).write_upload_object(storage_path=upload["storage_path"], content=content)
    confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/confirm",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert confirm.status_code == 200
    assert UploadProcessingWorker().process_one().processed is True
    return workspace_id, product_id, upload["upload_id"]


def _create_product(workspace_id: str) -> str:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"product_name": f"Monitoring Product {uuid4()}", "target_acos": "0.5000", "default_budget": "10.0000", "default_bid": "1.0000"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _sp_report_csv() -> str:
    header = "Start Date,End Date,Portfolio name,Currency,Campaign Name,Ad Group Name,Retailer,Country,Targeting,Match Type,Customer Search Term,Impressions,Clicks,Click-Thru Rate (CTR),Cost Per Click (CPC),Spend,7 Day Total Sales ,Total Advertising Cost of Sales (ACOS) ,Total Return on Advertising Spend (ROAS),7 Day Total Orders (#),7 Day Total Units (#),7 Day Conversion Rate,7 Day Advertised SKU Units (#),7 Day Other SKU Units (#),7 Day Advertised SKU Sales ,7 Day Other SKU Sales "
    rows = [
        "2026-05-01,2026-05-07,,USD,Camp A,Group A,Amazon,US,asin=\"b001\",-,pause term,100,25,0.25,1.00,25,0,,0,0,0,0,0,0,0,0",
        "2026-05-01,2026-05-07,,USD,Camp A,Group A,Amazon,US,asin=\"b002\",-,negative term,80,12,0.15,0.67,8,0,,0,0,0,0,0,0,0,0",
        "2026-05-01,2026-05-07,,USD,Camp B,Group B,Amazon,US,keyword=\"x\",exact,decrease term,100,12,0.12,0.67,8,10,0.8,1.25,1,1,0.08,1,0,10,0",
        "2026-05-01,2026-05-07,,USD,Camp B,Group B,Amazon,US,keyword=\"y\",exact,watch term,100,8,0.08,0.63,5,20,0.25,4,2,2,0.25,2,0,20,0",
        "2026-05-01,2026-05-07,,USD,Camp C,Group C,Amazon,US,keyword=\"z\",broad,increase term,20,1,0.05,1.00,1,0,,0,0,0,0,0,0,0,0",
    ]
    return "\n".join([header, *rows])


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    for workspace_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=workspace_id, job_id=job_id, status=JobStatus.CANCELLED)
