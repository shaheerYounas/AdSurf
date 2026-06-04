from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app
from apps.api.app.repositories.jobs import get_job_repository
from apps.api.app.schemas.jobs import JobStatus
from apps.api.app.services.storage import LocalFakeStorageService
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker
from apps.api.app.services.agent_registry import AGENT_WORKFLOW_ORDER

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
    assert data["workflow_id"]
    assert data["import_record"]["status"] == "needs_mapping"
    assert data["detection"]["product_identifiers_available"] == ["asin", "sku", "product_name"]
    assert any(entity["entity_type"] == "account" and entity["metrics_json"]["clicks"] == 22 for entity in data["entities"])
    assert any(entity["entity_type"] == "search_term" and entity["customer_search_term"] == "blue running shoes" for entity in data["entities"])
    assert len(data["product_mapping_suggestions"]) == 1
    assert data["product_mapping_suggestions"][0]["asin"] == "B0NEWASIN1"

    workflow = client.get(f"/v1/workspaces/{workspace_id}/workflows/{data['workflow_id']}", headers=auth_headers(workspace_id))
    events = client.get(f"/v1/workspaces/{workspace_id}/workflows/{data['workflow_id']}/events", headers=auth_headers(workspace_id))
    gates = client.get(f"/v1/workspaces/{workspace_id}/approval-gates", headers=auth_headers(workspace_id, role="viewer"))
    graph_recommendations = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id, role="viewer"))
    assert workflow.status_code == 200
    assert workflow.json()["data"]["workflow"]["status"] in {"waiting_for_human", "succeeded"}
    assert workflow.json()["data"]["workflow"]["state_json"]["safety_boundaries"]["executes_live_amazon_change"] is False
    assert events.status_code == 200
    assert any(event["event_type"] == "node_started" for event in events.json()["data"])
    assert gates.status_code == 200
    assert gates.json()["data"]
    assert gates.json()["data"][0]["status"] == "waiting"
    assert graph_recommendations.status_code == 200
    assert any(item["account_import_id"] == data["import_record"]["id"] for item in graph_recommendations.json()["data"])

    approved_gate = client.post(
        f"/v1/workspaces/{workspace_id}/approval-gates/{gates.json()['data'][0]['id']}/approve",
        headers=auth_headers(workspace_id, role="approver"),
        json={"reason": "Reviewed gate during integration test"},
    )
    assert approved_gate.status_code == 200
    assert approved_gate.json()["data"]["status"] == "approved"


def test_account_import_agent_analysis_creates_runs_and_approval_only_recommendations(monkeypatch, tmp_path) -> None:
    workspace_id, account_import_id = _created_account_import(monkeypatch, tmp_path)

    analysis = client.post(
        f"/v1/workspaces/{workspace_id}/account-imports/{account_import_id}/run-analysis",
        headers=auth_headers(workspace_id, role="analyst"),
        json={},
    )
    workflow = client.get(f"/v1/workspaces/{workspace_id}/account-imports/{account_import_id}/agent-workflow", headers=auth_headers(workspace_id, role="viewer"))
    runs = client.get(f"/v1/workspaces/{workspace_id}/agent-runs?monitoring_import_id={account_import_id}", headers=auth_headers(workspace_id, role="viewer"))
    recommendations = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id, role="viewer"))

    assert analysis.status_code == 200
    assert analysis.json()["data"]["run_count"] == len(AGENT_WORKFLOW_ORDER)
    assert analysis.json()["data"]["recommendation_count"] >= 1
    assert workflow.status_code == 200
    workflow_data = workflow.json()["data"]
    assert [node["agent_id"] for node in workflow_data["nodes"]] == AGENT_WORKFLOW_ORDER
    assert all(node["status"] in {"succeeded", "skipped"} for node in workflow_data["nodes"][:-1])
    assert workflow_data["nodes"][-1]["agent_id"] == "human_approval_agent"
    assert any(event["event_type"] == "waiting_for_human" for event in workflow_data["events"])
    assert runs.status_code == 200
    assert all(run["can_mutate_live_amazon_ads"] is False for run in runs.json()["data"])
    assert recommendations.status_code == 200
    assert recommendations.json()["data"]
    assert all(item["status"] == "pending_approval" for item in recommendations.json()["data"])
    assert all(item["approval_boundary"]["executes_live_amazon_change"] is False for item in recommendations.json()["data"])


def test_account_import_workflow_controls_are_audited_and_safe(monkeypatch, tmp_path) -> None:
    workspace_id, _, workflow_id = _created_account_import(monkeypatch, tmp_path, include_workflow=True)

    pause = client.post(
        f"/v1/workspaces/{workspace_id}/workflows/{workflow_id}/pause",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"reason": "QA pause check"},
    )
    stop = client.post(
        f"/v1/workspaces/{workspace_id}/workflows/{workflow_id}/stop",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"reason": "QA stop check"},
    )
    events = client.get(f"/v1/workspaces/{workspace_id}/workflows/{workflow_id}/events", headers=auth_headers(workspace_id, role="viewer"))

    assert pause.status_code == 200
    assert pause.json()["data"]["status"] == "paused"
    assert pause.json()["data"]["state_json"]["control_reason"] == "QA pause check"
    assert stop.status_code == 200
    assert stop.json()["data"]["status"] == "stopped"
    assert events.status_code == 200
    assert any(event["event_type"] == "agent_paused" for event in events.json()["data"])
    assert any(event["event_type"] == "agent_stopped" and event["metadata_json"]["executes_live_amazon_change"] is False for event in events.json()["data"])


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    repository.clear_queued_jobs()


def _created_account_import(monkeypatch, tmp_path, include_workflow: bool = False):
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
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
    upload = init.json()["data"]
    LocalFakeStorageService(root=str(tmp_path)).write_upload_object(storage_path=upload["storage_path"], content=content)
    client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )
    UploadProcessingWorker().process_one()
    created = client.post(
        f"/v1/workspaces/{workspace_id}/account-imports",
        headers=auth_headers(workspace_id),
        json={"upload_id": upload["upload_id"]},
    )
    data = created.json()["data"]
    if include_workflow:
        return workspace_id, data["import_record"]["id"], data["workflow_id"]
    return workspace_id, data["import_record"]["id"]
