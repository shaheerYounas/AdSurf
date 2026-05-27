from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.repositories.monitoring import new_monitoring_import
from apps.api.app.schemas.monitoring import MonitoringSnapshot
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.services import monitoring_metrics
from apps.api.app.services.ai_client import AiJsonResponse
from apps.api.app.services.ai_recommendation_brain import AiRecommendationBrain, DEEPSEEK_DECISION_SOURCE, FALLBACK_DECISION_SOURCE, build_deterministic_recommendations


class _FakeAiClient:
    provider = "deepseek"
    model = "deepseek-chat"

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete_json(self, *, messages, timeout_seconds=None):
        return AiJsonResponse(provider=self.provider, model=self.model, content_json=self.payload, latency_ms=12)


def test_valid_ai_recommendation_is_converted_to_pending_approval_record() -> None:
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    rollups = monitoring_metrics.build_performance_rollups([snapshot])
    brain = AiRecommendationBrain(client=_FakeAiClient(_ai_payload(executes_live=False)))

    result = brain.generate(product=product, import_record=import_record, snapshots=[snapshot], rollups=rollups, data_quality_warnings=[])

    assert result.used_ai is True
    assert result.ai_run.status == "succeeded"
    assert len(result.recommendations) == 1
    recommendation = result.recommendations[0]
    assert recommendation.status == "pending_approval"
    assert recommendation.evidence_json["decision_source"] == DEEPSEEK_DECISION_SOURCE
    assert recommendation.evidence_json["ai_model"] == "deepseek-chat"
    assert recommendation.explanation_json["approval_required"] is True
    assert recommendation.proposed_action_json["executes_live_amazon_change"] is False


def test_unsafe_ai_output_with_live_execution_is_rejected() -> None:
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    rollups = monitoring_metrics.build_performance_rollups([snapshot])
    brain = AiRecommendationBrain(client=_FakeAiClient(_ai_payload(executes_live=True)))

    result = brain.generate(product=product, import_record=import_record, snapshots=[snapshot], rollups=rollups, data_quality_warnings=[])

    assert result.used_ai is False
    assert result.recommendations == []
    assert result.ai_run.status == "failed"
    assert any("executes_live_amazon_change must be false" in error for error in result.validation_errors)


def test_invalid_snapshot_reference_is_rejected() -> None:
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    payload = _ai_payload(executes_live=False)
    payload["recommendations"][0]["campaign_name"] = "Missing Campaign"
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    result = AiRecommendationBrain(client=_FakeAiClient(payload)).generate(product=product, import_record=import_record, snapshots=[snapshot], rollups=rollups, data_quality_warnings=[])

    assert result.used_ai is False
    assert any("does not reference an entity" in error for error in result.validation_errors)


def test_direct_mutation_instruction_is_rejected_even_when_flags_are_safe() -> None:
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    payload = _ai_payload(executes_live=False)
    payload["recommendations"][0]["reasoning_summary"] = "Automatically apply this negative in Amazon because approval is not needed."
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    result = AiRecommendationBrain(client=_FakeAiClient(payload)).generate(product=product, import_record=import_record, snapshots=[snapshot], rollups=rollups, data_quality_warnings=[])

    assert result.used_ai is False
    assert any("mutation or approval-bypass" in error for error in result.validation_errors)


def test_deterministic_fallback_source_tracking_uses_failed_ai_run_metadata() -> None:
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    failed_ai = AiRecommendationBrain(client=_FakeAiClient(_ai_payload(executes_live=True))).generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=monitoring_metrics.build_performance_rollups([snapshot]),
        data_quality_warnings=[],
    ).ai_run

    recommendations = build_deterministic_recommendations(product=product, import_record=import_record, snapshots=[snapshot], decision_source=FALLBACK_DECISION_SOURCE, ai_run=failed_ai)

    assert recommendations[0].evidence_json["decision_source"] == FALLBACK_DECISION_SOURCE
    assert recommendations[0].evidence_json["ai_run_id"] == str(failed_ai.id)
    assert recommendations[0].proposed_action_json["requires_human_approval"] is True
    assert recommendations[0].proposed_action_json["executes_live_amazon_change"] is False


def _product() -> ProductProfile:
    now = datetime.now(UTC)
    return ProductProfile(id=uuid4(), workspace_id=uuid4(), product_name="AI Product", target_acos=Decimal("0.5000"), default_budget=Decimal("10.0000"), default_bid=Decimal("1.0000"), marketplace="US", currency="USD", created_at=now, updated_at=now)


def _import(product: ProductProfile):
    return new_monitoring_import(workspace_id=product.workspace_id, product_id=product.id, upload_id=uuid4(), parse_run_id=uuid4(), created_by=str(uuid4()))


def _snapshot(product: ProductProfile, import_record) -> MonitoringSnapshot:
    return MonitoringSnapshot(
        id=uuid4(),
        workspace_id=product.workspace_id,
        product_id=product.id,
        monitoring_import_id=import_record.id,
        upload_id=import_record.upload_id,
        parse_run_id=import_record.parse_run_id,
        source_row_id=uuid4(),
        campaign_name="Campaign A",
        ad_group_name="Group A",
        targeting='keyword="waste"',
        match_type="exact",
        customer_search_term="waste term",
        start_date="2026-05-01",
        end_date="2026-05-07",
        impressions=100,
        clicks=20,
        spend=Decimal("20.0000"),
        sales=Decimal("0.0000"),
        orders=0,
        units=0,
        cpc=Decimal("1.0000"),
        ctr=Decimal("0.2000"),
        cvr=Decimal("0.0000"),
        acos=None,
        roas=Decimal("0.0000"),
        raw_metrics_json={},
        created_at=datetime.now(UTC),
    )


def _ai_payload(*, executes_live: bool) -> dict:
    return {
        "recommendations": [
            {
                "entity_type": "search_term",
                "recommendation_type": "add_negative_exact",
                "priority": "high",
                "confidence": "high",
                "campaign_name": "Campaign A",
                "ad_group_name": "Group A",
                "targeting": 'keyword="waste"',
                "customer_search_term": "waste term",
                "reasoning_summary": "High clicks and spend with no orders support a negative exact review.",
                "evidence": {
                    "metrics_used": {"clicks": 20, "spend": "20.0000", "orders": 0},
                    "main_signals": ["20 clicks", "no orders"],
                    "risk_factors": ["May block a term if product relevance is misunderstood."],
                    "data_limitations": ["Uploaded report evidence only."],
                },
                "proposed_action": {
                    "action": "add_negative_exact",
                    "action_level": "search_term",
                    "suggested_bid_multiplier": None,
                    "negative_match_type": "exact",
                    "requires_human_approval": True,
                    "executes_live_amazon_change": executes_live,
                },
            }
        ],
        "dashboard_summary": {
            "headline": "1 AI recommendation needs review.",
            "top_winners": [],
            "top_wasters": ["waste term"],
            "main_risks": ["No-order spend"],
            "next_best_actions": ["Review negative exact recommendation."],
        },
    }
