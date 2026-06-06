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
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    get_settings.cache_clear()
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)

    import_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    assert import_response.status_code == 200
    import_body = import_response.json()["data"]

    duplicate_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    assert duplicate_response.status_code == 200
    duplicate_body = duplicate_response.json()["data"]
    assert duplicate_body["already_imported"] is True
    assert duplicate_body["import_record"]["id"] == import_body["import_record"]["id"]
    assert duplicate_body["job_id"] is None

    result = MonitoringWorker().process_one()
    assert result.processed is True
    assert result.import_record.status == "succeeded"

    recommendations_response = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id))
    recommendations = recommendations_response.json()["data"]
    types = {recommendation["recommendation_type"] for recommendation in recommendations}

    assert recommendations_response.status_code == 200
    assert import_body["import_record"]["status"] == "queued"
    assert {
        "keep_running",
        "increase_bid",
        "decrease_bid",
        "pause_review",
        "add_negative_exact",
        "add_negative_phrase",
        "move_to_exact",
        "watch_lock",
        "data_quality_review",
        "budget_review",
    }.issubset(types)
    assert all(recommendation["status"] == "pending_approval" for recommendation in recommendations)
    assert all(recommendation["explanation_json"]["approval_required"] is True for recommendation in recommendations)
    assert all(recommendation["evidence_json"]["approval_boundary"]["executes_live_amazon_change"] is False for recommendation in recommendations)
    assert all(recommendation["evidence_json"]["decision_source"] == "fallback_rules" for recommendation in recommendations)
    assert all(recommendation["evidence_json"]["ai_provider"] == "deepseek" for recommendation in recommendations)

    monitoring = client.get(f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring", headers=auth_headers(workspace_id))
    assert monitoring.status_code == 200
    monitoring_data = monitoring.json()["data"]
    assert "No AI final decision" in monitoring_data["agent_summary"]["stakeholder_note"]
    assert monitoring_data["summary_metrics"]["rows_analyzed"] == 11
    assert monitoring_data["summary_metrics"]["recommendations_generated"] == len(recommendations)
    assert monitoring_data["summary_metrics"]["no_live_amazon_changes"] is True
    assert monitoring_data["action_recommendation_counts"]["add_negative_exact"] == 1
    assert monitoring_data["issue_counts"]["info"] >= 1

    agent_runs = client.get(f"/v1/workspaces/{workspace_id}/products/{product_id}/agent-runs", headers=auth_headers(workspace_id))
    assert agent_runs.status_code == 200
    agent_names = {run["agent_name"] for run in agent_runs.json()["data"]}
    assert {"monitoring_recommendation_brain", "performance_import_agent", "metrics_analysis_agent", "bid_optimization_agent", "negative_keyword_agent", "pause_review_agent", "stakeholder_reporting_agent"}.issubset(agent_names)
    assert all(run["product_id"] == product_id for run in agent_runs.json()["data"])

    audit_repository = get_audit_log_repository()
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="monitoring_import.queued", object_id=UUID(import_body["import_record"]["id"])) == 1


def test_recommendation_approval_and_rejection_require_notes_and_scope(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
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
    assert approved.json()["data"]["proposed_action_json"]["executes_live_amazon_change"] is False
    assert second_decision.status_code == 409
    audit_repository = get_audit_log_repository()
    approval_events = [
        record
        for record in audit_repository.records
        if record["workspace_id"] == UUID(workspace_id)
        and record["event_type"] == "recommendation.approved"
        and record["object_id"] == UUID(recommendation["id"])
    ]
    assert approval_events[-1]["metadata_json"]["execution_boundary"] == "no_live_amazon_change"
    assert approval_events[-1]["metadata_json"]["approval_updates_app_state_only"] is True


def test_recommendations_can_be_deleted_singly_and_in_bulk_with_audit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    recommendations = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"]

    viewer_delete = client.delete(
        f"/v1/workspaces/{workspace_id}/recommendations/{recommendations[0]['id']}",
        headers=auth_headers(workspace_id, role="viewer"),
    )
    deleted_one = client.delete(
        f"/v1/workspaces/{workspace_id}/recommendations/{recommendations[0]['id']}",
        headers=auth_headers(workspace_id, role="approver"),
    )
    deleted_bulk = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/bulk-delete",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"recommendation_ids": [recommendations[1]["id"], recommendations[2]["id"]]},
    )
    remaining = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"]

    assert viewer_delete.status_code == 403
    assert deleted_one.status_code == 200
    assert deleted_one.json()["data"]["deleted"] is True
    assert deleted_bulk.status_code == 200
    assert deleted_bulk.json()["data"]["deleted_count"] == 2
    assert len(remaining) == len(recommendations) - 3
    assert {item["id"] for item in recommendations[:3]}.isdisjoint({item["id"] for item in remaining})
    audit_repository = get_audit_log_repository()
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="recommendation.deleted", object_id=UUID(recommendations[0]["id"])) == 1
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="recommendation.bulk_deleted", object_id=UUID(recommendations[1]["id"])) == 1


def test_deepseek_mode_missing_key_fails_safely_without_recommendations(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()

    import_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    import_body = import_response.json()["data"]

    result = MonitoringWorker().process_one()

    assert result.processed is True
    assert result.import_record.status == "failed"
    recommendations = client.get(f"/v1/workspaces/{workspace_id}/products/{product_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"]
    assert recommendations == []
    agent_runs = client.get(f"/v1/workspaces/{workspace_id}/products/{product_id}/agent-runs", headers=auth_headers(workspace_id)).json()["data"]
    brain_run = next(run for run in agent_runs if run["agent_name"] == "monitoring_recommendation_brain")
    assert brain_run["status"] == "failed"
    assert "DEEPSEEK_API_KEY" in brain_run["output_json"]["error"]
    audit_repository = get_audit_log_repository()
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="monitoring_import.ai_recommendations_failed", object_id=UUID(import_body["import_record"]["id"])) == 1


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
        "2026-05-01,2026-05-07,,USD,Camp A,Group A,Amazon,US,asin=\"b001\",exact,pause term,100,25,0.25,1.00,25,0,,0,0,0,0,0,0,0,0",
        "2026-05-01,2026-05-07,,USD,Camp A,Group A,Amazon,US,asin=\"b002\",broad,negative phrase term,80,16,0.20,0.63,10,0,,0,0,0,0,0,0,0,0",
        "2026-05-01,2026-05-07,,USD,Camp A,Group A,Amazon,US,keyword=\"exact waste\",exact,negative exact term,80,16,0.20,0.75,12,0,,0,0,0,0,0,0,0,0",
        "2026-05-01,2026-05-07,,USD,Camp B,Group B,Amazon,US,keyword=\"x\",exact,decrease term,100,12,0.12,0.67,8,10,0.8,1.25,1,1,0.08,1,0,10,0",
        "2026-05-01,2026-05-07,,USD,Camp B,Group B,Amazon,US,keyword=\"move\",broad,move exact term,100,8,0.08,0.63,5,20,0.25,4,2,2,0.25,2,0,20,0",
        "2026-05-01,2026-05-07,,USD,Camp B,Group B,Amazon,US,keyword=\"y\",exact,watch term,100,8,0.08,0.63,5,20,0.25,4,2,2,0.25,2,0,20,0",
        "2026-05-01,2026-05-07,,USD,Camp C,Group C,Amazon,US,keyword=\"z\",broad,increase term,20,1,0.05,1.00,1,0,,0,0,0,0,0,0,0,0",
        "2026-05-01,2026-05-07,,USD,Camp C,Group C,Amazon,US,keyword=\"scale\",exact,scaling term,80,8,0.10,0.50,4,20,0.2,5,2,2,0.25,2,0,20,0",
        "2026-05-01,2026-05-07,,USD,Camp C,Group C,Amazon,US,keyword=\"budget\",exact,budget term,100,20,0.20,0.45,9,30,0.3,3.3333,3,3,0.15,3,0,30,0",
        "2026-05-01,2026-05-07,,USD,Camp C,Group C,Amazon,US,keyword=\"keep\",exact,keep term,100,5,0.05,0.60,3,5,0.6,1.6667,1,1,0.20,1,0,5,0",
        "2026-05-01,2026-05-07,,USD,Camp D,Group D,Amazon,US,keyword=\"quality\",exact,quality term,5,10,2.00,0.20,2,0,,0,0,0,0,0,0,0,0",
    ]
    return "\n".join([header, *rows])


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    for workspace_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=workspace_id, job_id=job_id, status=JobStatus.CANCELLED)
