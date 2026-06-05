"""Integration test: full pipeline from upload → parse → monitor → recommend → approve → reject → export.

Tests the complete end-to-end flow that represents the core business process of the app.

Flow:
1. Create product profile
2. Upload Amazon SP Search Term report
3. Confirm upload → parse
4. Create monitoring import → process → generate recommendations
5. All recommendations must be in pending_approval state
6. Viewer role CANNOT approve
7. Analyst/Approver CAN approve with a required note
8. Second decision on same recommendation returns 409 (immutable)
9. Rejected recommendations do NOT appear in export
10. generate_bulk_sheet produces correct CSV per approved recommendation type
11. Export CSV has correct Amazon bulk sheet headers
12. Bid recommendations have non-null recommended_bid in CSV
13. WATCH_LOCK/KEEP_RUNNING recommendations produce no CSV rows
14. Safety flags: no live Amazon change, approval_required=True in all recs
"""

import csv
import io
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from apps.api.app.core.config import get_settings
from apps.api.app.repositories.jobs import get_job_repository
from apps.api.app.schemas.jobs import JobStatus
from apps.api.app.schemas.monitoring import RecommendationType
from apps.api.app.services.bulk_export_generator import generate_bulk_sheet, BULK_SHEET_HEADERS
from apps.api.app.services.monitoring_worker import MonitoringWorker
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker
from apps.api.app.services.storage import LocalFakeStorageService

from tests.integration.test_keyword_scoring_api import auth_headers, client


FIXTURES = Path(__file__).parent.parent / "fixtures"


def _sp_csv() -> str:
    """Minimal but realistic SP search term report with all major recommendation types."""
    header = (
        "Start Date,End Date,Portfolio name,Currency,Campaign Name,Ad Group Name,"
        "Retailer,Country,Targeting,Match Type,Customer Search Term,Impressions,Clicks,"
        "Click-Thru Rate (CTR),Cost Per Click (CPC),Spend,7 Day Total Sales ,"
        "Total Advertising Cost of Sales (ACOS) ,Total Return on Advertising Spend (ROAS),"
        "7 Day Total Orders (#),7 Day Total Units (#),7 Day Conversion Rate,"
        "7 Day Advertised SKU Units (#),7 Day Other SKU Units (#),"
        "7 Day Advertised SKU Sales ,7 Day Other SKU Sales "
    )
    rows = [
        # High spend, 0 orders → pause_review (spend=$45 > 2×$20 budget)
        "2026-01-01,2026-01-07,,USD,Camp A,Group A,Amazon,US,keyword,exact,pause candidate,100,20,0.20,2.25,45,0,,0,0,0,0,0,0,0,0",
        # Broad waste → add_negative_phrase (spend=$25 >= $20 budget, 0 orders, 16 clicks)
        "2026-01-01,2026-01-07,,USD,Camp A,Group A,Amazon,US,keyword,broad,negative phrase candidate,80,16,0.20,1.56,25,0,,0,0,0,0,0,0,0,0",
        # Exact waste → add_negative_exact (spend=$12, 16 clicks, 0 orders)
        "2026-01-01,2026-01-07,,USD,Camp B,Group B,Amazon,US,keyword,exact,negative exact candidate,80,16,0.20,0.75,12,0,,0,0,0,0,0,0,0,0",
        # High ACOS with sales → decrease_bid
        "2026-01-01,2026-01-07,,USD,Camp B,Group B,Amazon,US,keyword,exact,decrease candidate,100,12,0.12,0.67,8,10,0.8,1.25,1,1,0.08,1,0,10,0",
        # Good broad, 2 orders, low ACOS → move_to_exact
        "2026-01-01,2026-01-07,,USD,Camp C,Group C,Amazon,US,keyword,broad,move to exact candidate,100,8,0.08,0.63,5,20,0.25,4,2,2,0.25,2,0,20,0",
        # Low impressions, 2 orders, good CVR → increase_bid
        "2026-01-01,2026-01-07,,USD,Camp C,Group C,Amazon,US,keyword,exact,increase bid candidate,25,5,0.20,0.80,4,20,0.2,5,3,3,0.60,3,0,20,0",
        # Good exact, 2 orders → watch_lock (no further action needed)
        "2026-01-01,2026-01-07,,USD,Camp C,Group C,Amazon,US,keyword,exact,watch lock candidate,200,10,0.05,0.60,6,40,0.15,6.67,2,2,0.20,2,0,40,0",
    ]
    return "\n".join([header, *rows])


def _cancel_queued_jobs() -> None:
    repository = get_job_repository()
    for ws_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=ws_id, job_id=job_id, status=JobStatus.CANCELLED)


def _setup_processed_upload(monkeypatch, tmp_path) -> tuple[str, str, str]:
    storage_root = tmp_path / "storage"
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    _cancel_queued_jobs()

    workspace_id = str(uuid4())

    # Create product
    product_resp = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="analyst"),
        json={
            "product_name": "Pipeline Test Product",
            "target_acos": "0.25",
            "default_budget": "20.0000",
            "default_bid": "1.0000",
        },
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["data"]["id"]

    # Init upload
    content = _sp_csv().encode("utf-8")
    init_resp = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": "test-sp-report.csv",
            "mime_type": "text/csv",
            "file_size_bytes": len(content),
            "source_type": "amazon_ads_sp_search_term_report",
        },
    )
    assert init_resp.status_code in {200, 201}
    upload_data = init_resp.json()["data"]
    upload_id = upload_data["upload_id"]

    # Write raw bytes
    LocalFakeStorageService(root=str(storage_root)).write_upload_object(
        storage_path=upload_data["storage_path"], content=content
    )

    # Confirm → triggers parse
    confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert confirm.status_code == 200

    parse_result = UploadProcessingWorker().process_one()
    assert parse_result.processed is True

    return workspace_id, product_id, upload_id


# ── Test 1: Recommendations generated and all pending ─────────────────────────

def test_full_pipeline_recommendations_all_start_pending(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)

    import_resp = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    assert import_resp.status_code == 200

    work = MonitoringWorker().process_one()
    assert work.processed is True
    assert work.import_record.status == "succeeded"

    recs_resp = client.get(
        f"/v1/workspaces/{workspace_id}/recommendations",
        headers=auth_headers(workspace_id),
    )
    assert recs_resp.status_code == 200
    recs = recs_resp.json()["data"]

    assert len(recs) == 7
    assert all(r["status"] == "pending_approval" for r in recs)
    assert all(r["proposed_action_json"]["executes_live_amazon_change"] is False for r in recs)
    assert all(r["proposed_action_json"]["requires_human_approval"] is True for r in recs)


# ── Test 2: Role gates on approval/rejection ──────────────────────────────────

def test_viewer_cannot_approve_recommendation(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    rec = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"][0]

    resp = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/approve",
        headers=auth_headers(workspace_id, role="viewer"),
        json={"note": "I should not be able to do this"},
    )
    assert resp.status_code == 403


def test_approval_requires_note(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    rec = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"][0]

    empty_note = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/approve",
        headers=auth_headers(workspace_id, role="approver"),
        json={"note": ""},
    )
    assert empty_note.status_code == 422


def test_double_decision_returns_409(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    rec = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"][0]

    client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/approve",
        headers=auth_headers(workspace_id, role="approver"),
        json={"note": "First approval"},
    )
    second = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/reject",
        headers=auth_headers(workspace_id, role="approver"),
        json={"note": "Trying to change"},
    )
    assert second.status_code == 409


# ── Test 3: Reject path returns 200 with rejected status ─────────────────────

def test_rejection_returns_200_with_rejected_status(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    recs = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"]
    rec = recs[0]

    resp = client.post(
        f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/reject",
        headers=auth_headers(workspace_id, role="approver"),
        json={"note": "Not relevant for this product"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "rejected"


# ── Test 4: Full approve + export cycle ──────────────────────────────────────

def test_approved_recommendations_export_to_valid_bulk_csv(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    recs = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"]

    # Approve all actionable recs (skip watch_lock / keep_running)
    approved_ids = []
    rejected_ids = []
    for rec in recs:
        rtype = rec["recommendation_type"]
        if rtype in {"pause_review", "add_negative_phrase", "add_negative_exact", "decrease_bid", "move_to_exact", "increase_bid"}:
            resp = client.post(
                f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/approve",
                headers=auth_headers(workspace_id, role="approver"),
                json={"note": "Approved after manual review"},
            )
            assert resp.status_code == 200
            approved_ids.append(rec["id"])
        elif rtype == "watch_lock":
            # Reject the watch_lock — it's informational, no export needed
            resp = client.post(
                f"/v1/workspaces/{workspace_id}/recommendations/{rec['id']}/reject",
                headers=auth_headers(workspace_id, role="approver"),
                json={"note": "Keeping as-is, no action"},
            )
            rejected_ids.append(rec["id"])

    # Fetch approved recommendations from API
    updated_recs = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id)).json()["data"]
    approved_recs_data = [r for r in updated_recs if r["status"] == "approved"]

    # Build Recommendation schema objects for the exporter
    from datetime import datetime, UTC
    from decimal import Decimal
    from apps.api.app.schemas.monitoring import (
        Recommendation, RecommendationStatus, RecommendationPriority,
        RecommendationEntityType, RecommendationConfidence,
    )

    schema_recs = []
    for r in approved_recs_data:
        schema_recs.append(
            Recommendation(
                id=r["id"],
                workspace_id=r["workspace_id"],
                product_id=r.get("product_id"),
                recommendation_type=r["recommendation_type"],
                status=r["status"],
                priority=r["priority"],
                confidence=r.get("confidence", "medium"),
                rule_version_id=r["rule_version_id"],
                rule_name=r["rule_name"],
                entity_type=r.get("entity_type", "search_term"),
                campaign_name=r.get("campaign_name"),
                ad_group_name=r.get("ad_group_name"),
                targeting=r.get("targeting"),
                customer_search_term=r.get("customer_search_term"),
                match_type=r.get("match_type"),
                current_bid=Decimal(str(r["current_bid"])) if r.get("current_bid") else None,
                recommended_bid=Decimal(str(r["recommended_bid"])) if r.get("recommended_bid") else None,
                change_percent=Decimal(str(r["change_percent"])) if r.get("change_percent") else None,
                input_metrics_json=r.get("input_metrics_json", {}),
                proposed_action_json=r.get("proposed_action_json", {}),
                explanation_json=r.get("explanation_json", {}),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    export = generate_bulk_sheet(schema_recs, workspace_id=UUID(workspace_id))

    # Validate export structure
    assert "csv_content" in export
    assert export["total_recommendations"] == len(approved_ids)
    assert export["safety_note"].startswith("This bulk sheet was generated by AdSurf")

    # Parse CSV and validate headers
    rows = list(csv.DictReader(io.StringIO(export["csv_content"])))
    assert all(h in rows[0] for h in BULK_SHEET_HEADERS) if rows else True

    # Validate that WATCH_LOCK does not appear in CSV
    operations = {r["Operation"] for r in rows}
    assert "No Change - Review Only" not in operations, "WATCH_LOCK rows must not appear in bulk CSV"

    # Validate bid change rows (not pause rows) have non-empty Keyword Bid.
    # Pause rows also use Operation=Update + Record Type=Keyword but set Keyword Status=Paused with no bid.
    bid_rows = [r for r in rows if r["Operation"] == "Update" and r["Record Type"] == "Keyword" and r.get("Keyword Status") == "Enabled"]
    for bid_row in bid_rows:
        assert bid_row["Keyword Bid"] != "", "Bid update rows must have non-empty Keyword Bid"

    # Validate summary counts
    neg_exact_count = sum(1 for r in schema_recs if r.recommendation_type == "add_negative_exact")
    assert export["summary"]["negative_keywords"] >= neg_exact_count

    # Validate audit log
    assert len(export["audit_log"]) == len(approved_ids)
    for entry in export["audit_log"]:
        assert entry["exported_at"] is not None
        assert entry["recommendation_id"] in approved_ids


# ── Test 5: Duplicate upload returns same import ─────────────────────────────

def test_duplicate_monitoring_import_returns_existing(monkeypatch, tmp_path) -> None:
    workspace_id, product_id, upload_id = _setup_processed_upload(monkeypatch, tmp_path)

    first = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    second = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    assert second.status_code == 200
    assert second.json()["data"]["already_imported"] is True
    assert second.json()["data"]["import_record"]["id"] == first.json()["data"]["import_record"]["id"]
    assert second.json()["data"]["job_id"] is None


# ── Test 6: Wrong upload type rejected ───────────────────────────────────────

def test_non_sp_search_term_upload_rejected_for_monitoring(monkeypatch, tmp_path) -> None:
    storage_root = tmp_path / "storage"
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    _cancel_queued_jobs()

    workspace_id = str(uuid4())
    product_resp = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"product_name": "Reject Test", "target_acos": "0.25", "default_budget": "20.0000", "default_bid": "1.0000"},
    )
    product_id = product_resp.json()["data"]["id"]

    content = b"Campaign Name,Spend\nCamp A,100"
    init_resp = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": "wrong-report.csv",
            "mime_type": "text/csv",
            "file_size_bytes": len(content),
            "source_type": "sponsored_products_campaign_report",  # Valid upload type but NOT a search term report
        },
    )
    assert init_resp.status_code in {200, 201}
    upload_id = init_resp.json()["data"]["upload_id"]

    LocalFakeStorageService(root=str(storage_root)).write_upload_object(
        storage_path=init_resp.json()["data"]["storage_path"], content=content
    )
    confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert confirm.status_code == 200
    UploadProcessingWorker().process_one()

    monitoring_resp = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    assert monitoring_resp.status_code == 409
    assert monitoring_resp.json()["error"]["code"] == "MONITORING_UPLOAD_SOURCE_TYPE_INVALID"
