from uuid import UUID

from apps.api.app.repositories.audit_logs import get_audit_log_repository

from tests.integration.test_keyword_review_api import _create_keyword_set, _scored_run, auth_headers, client


def test_campaign_plan_generation_approval_and_bulk_export(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    keyword_set = _create_keyword_set(workspace_id, scoring_run_id, name="Campaign input").json()["data"]

    plan_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{keyword_set['product_id']}/campaign-plans",
        headers=auth_headers(workspace_id),
        json={"approved_keyword_set_id": keyword_set["id"]},
    )
    plan = plan_response.json()["data"]

    assert plan_response.status_code == 200
    assert plan["status"] == "generated"
    assert plan["plan_json"]["hero_keyword"]["search_term"]
    assert all(keyword["search_term"] for campaign in plan["plan_json"]["campaigns"] for keyword in campaign["keywords"])

    blocked_export = client.post(
        f"/v1/workspaces/{workspace_id}/campaign-plans/{plan['id']}/exports",
        headers=auth_headers(workspace_id),
        json={"approval_note": "Approve export", "format": "csv"},
    )
    assert blocked_export.status_code == 409
    assert blocked_export.json()["error"]["code"] == "CAMPAIGN_PLAN_APPROVAL_REQUIRED"

    approved_response = client.post(
        f"/v1/workspaces/{workspace_id}/campaign-plans/{plan['id']}/approve",
        headers=auth_headers(workspace_id),
        json={"approval_note": "Reviewed campaign plan"},
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["data"]["status"] == "approved"

    export_response = client.post(
        f"/v1/workspaces/{workspace_id}/campaign-plans/{plan['id']}/exports",
        headers=auth_headers(workspace_id),
        json={"approval_note": "Approved bulk sheet handoff", "format": "csv"},
    )
    export_body = export_response.json()["data"]
    rows = export_body["export"]["rows_json"]

    assert export_response.status_code == 200
    assert export_body["export"]["status"] == "approved"
    assert any(row["Record Type"] == "Campaign" for row in rows)
    assert any(row["Record Type"] == "Keyword" for row in rows)
    assert all(row["Keyword Text"] != "" for row in rows if row["Record Type"] in {"Keyword", "Negative keyword"})

    download = client.get(export_body["download_url"], headers=auth_headers(workspace_id))
    assert download.status_code == 200
    assert "Campaign Name" in download.text

    audit_repository = get_audit_log_repository()
    workspace_uuid = UUID(workspace_id)
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="campaign_plan.generated", object_id=UUID(plan["id"])) == 1
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="campaign_plan.approved", object_id=UUID(plan["id"])) == 1
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="bulk_export.approved", object_id=UUID(export_body["export"]["id"])) == 1


def test_campaign_plan_blocks_empty_or_cross_workspace_keyword_sets(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    keyword_set = _create_keyword_set(workspace_id, scoring_run_id, name="Scoped").json()["data"]
    other_workspace_id = "00000000-0000-0000-0000-000000000099"

    response = client.post(
        f"/v1/workspaces/{other_workspace_id}/products/{keyword_set['product_id']}/campaign-plans",
        headers=auth_headers(other_workspace_id),
        json={"approved_keyword_set_id": keyword_set["id"]},
    )

    assert response.status_code in {403, 404}
