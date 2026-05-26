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
                "Impressions": 100,
                "Clicks": 10,
                "Spend": 12,
                "7 Day Total Sales ": 0,
                "7 Day Total Orders (#)": 0,
                "Total Advertising Cost of Sales (ACOS) ": None,
            }
        )
    ]

    snapshots, warnings = normalize_sp_search_term_rows(import_record=import_record, rows=rows)

    assert warnings == []
    assert snapshots[0].acos is None
    assert snapshots[0].spend == Decimal("12")
    assert snapshots[0].orders == 0


def test_sp_search_term_missing_required_columns_fails_closed() -> None:
    with pytest.raises(ApiError) as error:
        normalize_sp_search_term_rows(import_record=_import_record(), rows=[_row({"Campaign Name": "A"})])

    assert error.value.code == "MONITORING_REPORT_COLUMNS_MISSING"


def test_recommendation_rule_thresholds_create_expected_actions() -> None:
    import_record = _import_record()
    rows = [
        _row(_report_row("pause term", clicks=25, spend=25, sales=0, orders=0, impressions=100)),
        _row(_report_row("negative term", clicks=12, spend=8, sales=0, orders=0, impressions=80)),
        _row(_report_row("decrease term", clicks=12, spend=8, sales=10, orders=1, acos=0.8, impressions=100)),
        _row(_report_row("watch term", clicks=8, spend=5, sales=20, orders=2, acos=0.25, impressions=100)),
        _row(_report_row("increase term", clicks=1, spend=1, sales=0, orders=0, impressions=20)),
    ]
    snapshots, _ = normalize_sp_search_term_rows(import_record=import_record, rows=rows)

    recommendations = build_recommendations(product=ProductProfileCreate(product_name="Rules"), import_record=import_record, snapshots=snapshots)
    by_term = {recommendation.customer_search_term: recommendation for recommendation in recommendations}

    assert by_term["pause term"].recommendation_type == "pause_review"
    assert by_term["negative term"].recommendation_type == "negative_keyword_review"
    assert by_term["decrease term"].recommendation_type == "decrease_bid"
    assert by_term["watch term"].recommendation_type == "watch_lock"
    assert by_term["increase term"].recommendation_type == "increase_bid"
    assert all(recommendation.status == "pending_approval" for recommendation in recommendations)


def test_agent_summary_does_not_decide_recommendations() -> None:
    import_record = _import_record()
    snapshots, _ = normalize_sp_search_term_rows(import_record=import_record, rows=[_row(_report_row("negative term", clicks=12, spend=8, sales=0, orders=0))])
    recommendations = build_recommendations(product=ProductProfileCreate(product_name="Agent Safety"), import_record=import_record, snapshots=snapshots)

    ai_run = build_stakeholder_ai_run(workspace_id=import_record.workspace_id, recommendations=recommendations, snapshots=snapshots)

    assert ai_run.output_json["headline"].endswith("recommendations need human review before any ad change.")
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


def _report_row(term: str, *, clicks: int, spend: int | float, sales: int | float, orders: int, impressions: int = 100, acos: float | None = None) -> dict:
    return {
        "Campaign Name": "Campaign A",
        "Ad Group Name": "Group A",
        "Targeting": "asin=\"b000\"",
        "Match Type": "-",
        "Customer Search Term": term,
        "Impressions": impressions,
        "Clicks": clicks,
        "Spend": spend,
        "7 Day Total Sales ": sales,
        "7 Day Total Orders (#)": orders,
        "7 Day Total Units (#)": orders,
        "Total Advertising Cost of Sales (ACOS) ": acos,
        "Total Return on Advertising Spend (ROAS)": 0 if sales == 0 else sales / spend,
    }
