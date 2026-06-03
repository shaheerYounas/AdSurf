from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.schemas.keyword_review import ApprovedKeywordSetItem, ReviewedKeywordStatus
from apps.api.app.schemas.keyword_scoring import KeywordCandidateStatus
from apps.api.app.schemas.product_profiles import ProductProfile, ProductProfileStatus
from apps.api.app.services.campaign_generation import build_campaign_plan_json
from apps.api.app.services.monitoring_14day import Monitoring14DayService


def test_campaign_names_follow_pdf_convention() -> None:
    product = _product()
    items = [
        _keyword("coffee beans", 10, "1000"),
        _keyword("espresso beans", 8, "900"),
        _keyword("whole bean coffee", 7, "800"),
    ]

    plan = build_campaign_plan_json(product=product, keyword_set_id=uuid4(), items=items)

    hero_name = plan["campaigns"][0]["campaign_name"]
    assert hero_name.startswith("CoffeeMaker / SP / Manual / Exact / coffee beans / ")
    assert any("CoffeeMaker / SP / Manual / Phrase / Relevant1 / " in campaign["campaign_name"] for campaign in plan["campaigns"])
    assert plan["approval_boundary"]["requires_human_approval"] is True
    assert plan["approval_boundary"]["executes_live_amazon_change"] is False


def test_campaign_plan_safety_summary_flags_budget_duplicates_and_asins() -> None:
    product = _product()
    items = [
        _keyword("b076z4n4dp", 10, "1000"),
        _keyword("b076z4n4dp", 9, "1000"),
        _keyword("low volume term", 8, "0"),
        _keyword("term 1", 7, "100"),
        _keyword("term 2", 7, "100"),
        _keyword("term 3", 7, "100"),
        _keyword("term 4", 7, "100"),
        _keyword("term 5", 7, "100"),
        _keyword("term 6", 7, "100"),
        _keyword("term 7", 7, "100"),
        _keyword("term 8", 7, "100"),
        _keyword("term 9", 7, "100"),
        _keyword("term 10", 7, "100"),
        _keyword("term 11", 7, "100"),
        _keyword("term 12", 7, "100"),
        _keyword("term 13", 7, "100"),
        _keyword("term 14", 7, "100"),
        _keyword("term 15", 7, "100"),
        _keyword("term 16", 7, "100"),
        _keyword("term 17", 7, "100"),
        _keyword("term 18", 7, "100"),
        _keyword("term 19", 7, "100"),
        _keyword("term 20", 7, "100"),
        _keyword("term 21", 7, "100"),
        _keyword("term 22", 7, "100"),
        _keyword("term 23", 7, "100"),
        _keyword("term 24", 7, "100"),
        _keyword("term 25", 7, "100"),
        _keyword("term 26", 7, "100"),
        _keyword("term 27", 7, "100"),
    ]

    plan = build_campaign_plan_json(product=product, keyword_set_id=uuid4(), items=items)
    summary = plan["safety_summary"]

    assert summary["requires_budget_confirmation"] is True
    assert summary["requires_existing_campaign_duplicate_check"] is True
    assert "possible_asin_targeting" in summary["risk_labels"]
    assert "possible_duplicate" in summary["risk_labels"]
    assert "not_enough_data" in summary["risk_labels"]
    assert "high_risk" in summary["risk_labels"]


def test_monitoring_14day_service_increases_bids_then_locks_after_day7() -> None:
    results = Monitoring14DayService().simulate_14day_cycle(
        workspace_id=uuid4(),
        product_id=uuid4(),
        campaign_name="CoffeeMaker / SP / Manual / Exact / coffee beans / Jun 2",
        daily_budget=Decimal("10.0000"),
        starting_bid=Decimal("1.0000"),
    )

    assert len(results) == 14
    assert results[0].action == "increase_bid"
    assert results[0].suggested_bid == Decimal("1.1000")
    assert results[6].day7_checkpoint is True
    assert results[6].locked is True
    assert all(result.action == "watch_lock" for result in results[7:])


def test_competitor_route_imports_with_monitoring_service() -> None:
    import apps.api.app.api.v1.competitor as competitor_routes

    assert competitor_routes.router is not None


def _product() -> ProductProfile:
    now = datetime.now(UTC)
    return ProductProfile(
        id=uuid4(),
        workspace_id=uuid4(),
        product_name="CoffeeMaker",
        marketplace="US",
        currency="USD",
        target_acos=Decimal("0.5000"),
        default_budget=Decimal("10.0000"),
        default_bid=Decimal("1.0000"),
        status=ProductProfileStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _keyword(search_term: str, relevance_score: int, search_volume: str) -> ApprovedKeywordSetItem:
    now = datetime.now(UTC)
    return ApprovedKeywordSetItem(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        approved_keyword_set_id=uuid4(),
        scoring_run_id=uuid4(),
        keyword_candidate_id=uuid4(),
        search_term=search_term,
        search_volume=Decimal(search_volume),
        relevance_score=relevance_score,
        source_status=KeywordCandidateStatus.APPROVED,
        final_status=ReviewedKeywordStatus.APPROVED,
        created_at=now,
    )
