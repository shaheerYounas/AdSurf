from decimal import Decimal
from uuid import uuid4

import pytest

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.monitoring import new_monitoring_import
from apps.api.app.schemas.product_profiles import ProductProfileCreate
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.services.monitoring_rules import build_recommendations, build_stakeholder_ai_run, normalize_sp_search_term_rows


def test_sp_search_term_normalization_and_acos_zero_sales_handling() -> None:
    import_record = _import_record()
    rows = [
        _row(
            {
                "Campaign Name": "Campaign A",
                "Ad Group Name": "Group A",
                "Targeting": "asin=\"b000\"",
                "Customer Search Term": "bad term",
                "Start Date": "2026-05-01",
                "End Date": "2026-05-07",
                "Impressions": 100,
                "Clicks": 10,
                "Click-Thru Rate (CTR)": 0.1,
                "Cost Per Click (CPC)": 1.2,
                "Spend": 12,
                "7 Day Total Sales ": 0,
                "7 Day Total Orders (#)": 0,
                "7 Day Total Units (#)": 0,
                "7 Day Conversion Rate": 0,
                "Total Advertising Cost of Sales (ACOS) ": None,
                "Total Return on Advertising Spend (ROAS)": 0,
            }
        )
    ]

    snapshots, warnings = normalize_sp_search_term_rows(import_record=import_record, rows=rows)

    assert "SPEND_WITH_NO_SALES" not in {warning["code"] for warning in warnings}
    assert all(warning.get("severity") != "critical" for warning in warnings)
    assert snapshots[0].acos is None
    assert snapshots[0].spend == Decimal("12")
    assert snapshots[0].orders == 0


def test_sp_search_term_missing_required_columns_fails_closed() -> None:
    with pytest.raises(ApiError) as error:
        normalize_sp_search_term_rows(import_record=_import_record(), rows=[_row({"Campaign Name": "A"})])

    assert error.value.code == "MONITORING_REPORT_COLUMNS_MISSING"


def test_sp_search_term_base_columns_calculate_missing_derived_metrics() -> None:
    snapshots, warnings = normalize_sp_search_term_rows(
        import_record=_import_record(),
        rows=[
            _row(
                {
                    "Campaign Name": "Campaign A",
                    "Ad Group Name": "Group A",
                    "Targeting": "running shoes",
                    "Match Type": "exact",
                    "Customer Search Term": "blue running shoes",
                    "Impressions": 100,
                    "Clicks": 5,
                    "Spend": "5.00",
                    "Sales": "20.00",
                    "Orders": 1,
                }
            )
        ],
    )

    assert warnings == []
    assert snapshots[0].sales == Decimal("20.00")
    assert snapshots[0].orders == 1
    assert snapshots[0].ctr == Decimal("0.0500")
    assert snapshots[0].cpc == Decimal("1.0000")
    assert snapshots[0].cvr == Decimal("0.2000")
    assert snapshots[0].acos == Decimal("0.2500")
    assert snapshots[0].roas == Decimal("4.0000")


def test_product_detection_uses_advertised_product_columns_not_customer_search_term_asins() -> None:
    snapshots, warnings = normalize_sp_search_term_rows(
        import_record=_import_record(),
        rows=[
            _row({**_report_row("B099999999", clicks=5, spend=5, sales=10, orders=1), "Advertised ASIN": "B08SW1Y38V", "Advertised SKU": "SKU-1"}),
            _row({**_report_row("B088888888", clicks=5, spend=6, sales=12, orders=1), "Advertised ASIN": "B08KT7WD1L", "Advertised SKU": "SKU-2"}),
        ],
    )

    product_message = next(warning for warning in warnings if warning["code"] == "MULTI_PRODUCT_REPORT_DETECTED")

    assert len(snapshots) == 2
    assert product_message["severity"] == "warning"
    assert {group["asin"] for group in product_message["details"]["detected_product_groups"]} == {"B08SW1Y38V", "B08KT7WD1L"}
    assert "Customer Search Term ASINs" in product_message["details"]["profile_creation_rule"]


def test_recommendation_rule_thresholds_create_expected_phase_1_actions_and_evidence() -> None:
    import_record = _import_record()
    rows = [
        _row(_report_row("pause term", clicks=25, spend=25, sales=0, orders=0, impressions=100, match_type="exact")),
        _row(_report_row("negative phrase term", clicks=16, spend=10, sales=0, orders=0, impressions=80, match_type="broad")),
        _row(_report_row("weak negative exact term", clicks=12, spend=8, sales=0, orders=0, impressions=80, match_type="exact")),
        _row(_report_row("negative exact term", clicks=16, spend=12, sales=0, orders=0, impressions=80, match_type="exact")),
        _row(_report_row("decrease term", clicks=12, spend=8, sales=10, orders=1, acos=0.8, impressions=100, match_type="exact")),
        _row(_report_row("move exact term", clicks=8, spend=5, sales=20, orders=2, acos=0.25, impressions=100, match_type="broad")),
        _row(_report_row("watch term", clicks=8, spend=5, sales=20, orders=2, acos=0.25, impressions=100, match_type="exact")),
        _row(_report_row("increase term", clicks=1, spend=1, sales=0, orders=0, impressions=20, match_type="broad")),
        _row(_report_row("scaling term", clicks=8, spend=4, sales=20, orders=2, acos=0.2, impressions=80, match_type="exact")),
        _row(_report_row("keep term", clicks=5, spend=3, sales=5, orders=1, acos=0.6, impressions=100, match_type="exact")),
        _row(_report_row("quality term", clicks=10, spend=2, sales=0, orders=0, impressions=5, match_type="exact")),
    ]
    snapshots, _ = normalize_sp_search_term_rows(import_record=import_record, rows=rows)

    recommendations = build_recommendations(product=ProductProfileCreate(product_name="Rules"), import_record=import_record, snapshots=snapshots)
    by_term = {recommendation.customer_search_term: recommendation for recommendation in recommendations}

    assert by_term["pause term"].recommendation_type == "pause_review"
    assert by_term["pause term"].priority == "critical"
    assert by_term["negative phrase term"].recommendation_type == "add_negative_phrase"
    assert by_term["weak negative exact term"].recommendation_type == "watch_lock"
    assert by_term["negative exact term"].recommendation_type == "add_negative_exact"
    assert by_term["decrease term"].recommendation_type == "decrease_bid"
    assert by_term["decrease term"].proposed_action_json["suggested_bid_multiplier"] == "0.6250"
    assert by_term["decrease term"].proposed_action_json["recommended_bid"] == "0.6250"
    assert by_term["move exact term"].recommendation_type == "move_to_exact"
    assert by_term["watch term"].recommendation_type == "watch_lock"
    assert by_term["increase term"].recommendation_type == "watch_lock"
    assert by_term["scaling term"].recommendation_type == "increase_bid"
    assert by_term["scaling term"].proposed_action_json["suggested_bid_multiplier"] == "1.3000"
    assert by_term["keep term"].recommendation_type == "keep_running"
    assert by_term["quality term"].recommendation_type == "data_quality_review"
    assert all(recommendation.status == "pending_approval" for recommendation in recommendations)
    assert all(recommendation.confidence in {"low", "medium", "high"} for recommendation in recommendations)
    assert all(recommendation.evidence_json["approval_boundary"]["executes_live_amazon_change"] is False for recommendation in recommendations)
    assert by_term["move exact term"].evidence_json["campaign_performance"]["orders"] >= 1
    assert "cpa" in by_term["keep term"].current_metric_snapshot_json
    assert "condition_signals" in by_term["keep term"].evidence_json
    assert by_term["quality term"].proposed_action_json["data_quality_flags"] == ["clicks_exceed_impressions"]


def test_agent_summary_does_not_decide_recommendations() -> None:
    import_record = _import_record()
    snapshots, _ = normalize_sp_search_term_rows(import_record=import_record, rows=[_row(_report_row("negative term", clicks=12, spend=8, sales=0, orders=0))])
    recommendations = build_recommendations(product=ProductProfileCreate(product_name="Agent Safety"), import_record=import_record, snapshots=snapshots)

    ai_run = build_stakeholder_ai_run(workspace_id=import_record.workspace_id, recommendations=recommendations, snapshots=snapshots)

    assert ai_run.output_json["headline"].endswith("recommendations generated for human review.")
    assert ai_run.output_json["zero_order_spend"] == "8.0000"
    assert "No AI final decision" in ai_run.output_json["stakeholder_note"]
    assert recommendations[0].status == "pending_approval"


def _import_record():
    return new_monitoring_import(
        workspace_id=uuid4(),
        product_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        created_by=str(uuid4()),
    )


def _row(data: dict) -> ParsedUploadRow:
    return ParsedUploadRow(id=uuid4(), row_number=2, row_data_json=data, row_hash=str(uuid4()))


def _report_row(term: str, *, clicks: int, spend: int | float, sales: int | float, orders: int, impressions: int = 100, acos: float | None = None, match_type: str = "-") -> dict:
    return {
        "Campaign Name": "Campaign A",
        "Ad Group Name": "Group A",
        "Targeting": "asin=\"b000\"",
        "Match Type": match_type,
        "Customer Search Term": term,
        "Start Date": "2026-05-01",
        "End Date": "2026-05-07",
        "Impressions": impressions,
        "Clicks": clicks,
        "Click-Thru Rate (CTR)": 0 if impressions == 0 else clicks / impressions,
        "Cost Per Click (CPC)": 0 if clicks == 0 else spend / clicks,
        "Spend": spend,
        "7 Day Total Sales ": sales,
        "7 Day Total Orders (#)": orders,
        "7 Day Total Units (#)": orders,
        "Total Advertising Cost of Sales (ACOS) ": acos,
        "Total Return on Advertising Spend (ROAS)": 0 if sales == 0 else sales / spend,
        "7 Day Conversion Rate": 0 if clicks == 0 else orders / clicks,
    }
