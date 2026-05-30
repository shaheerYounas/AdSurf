"""Integration tests for the AI recommendation brain's new behaviors:
retry loop, deterministic confidence override, critic, and pattern memory."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.repositories.monitoring import new_monitoring_import
from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    RecommendationConfidence,
    RecommendationPriority,
    RecommendationType,
)
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.services import monitoring_metrics
from apps.api.app.services.ai_client import AiJsonResponse
from apps.api.app.services.ai_recommendation_brain import AiRecommendationBrain
from apps.api.app.services.optimization_memory import PatternKey, PatternOutcome, pattern_key_to_str


class _ScriptedClient:
    """AI client that returns a queued sequence of payloads, one per call."""

    provider = "deepseek"
    model = "deepseek-chat"

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[list[dict]] = []

    def complete_json(self, *, messages, timeout_seconds=None):
        self.calls.append(list(messages))
        payload = self.payloads.pop(0) if self.payloads else self.payloads[-1]
        return AiJsonResponse(provider=self.provider, model=self.model, content_json=payload, latency_ms=10)


def _product() -> ProductProfile:
    now = datetime.now(UTC)
    return ProductProfile(
        id=uuid4(),
        workspace_id=uuid4(),
        product_name="P",
        target_acos=Decimal("0.30"),
        default_budget=Decimal("10.0000"),
        default_bid=Decimal("1.0000"),
        marketplace="US",
        currency="USD",
        created_at=now,
        updated_at=now,
    )


def _import(product):
    return new_monitoring_import(
        workspace_id=product.workspace_id,
        product_id=product.id,
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        created_by=str(uuid4()),
    )


def _snapshot(product, import_record, *, clicks=30, orders=0, spend="35.00", sales="0.00", match_type="exact", term="waste term") -> MonitoringSnapshot:
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
        match_type=match_type,
        customer_search_term=term,
        start_date="2026-05-01",
        end_date="2026-05-14",
        impressions=max(clicks * 10, 1),
        clicks=clicks,
        spend=Decimal(spend),
        sales=Decimal(sales),
        orders=orders,
        units=orders,
        cpc=Decimal("1.0000"),
        ctr=Decimal("0.1000"),
        cvr=Decimal("0.0500") if orders > 0 else Decimal("0.0000"),
        acos=Decimal("0.50") if orders > 0 else None,
        roas=Decimal("2.00") if orders > 0 else Decimal("0.0000"),
        raw_metrics_json={},
        created_at=datetime.now(UTC),
    )


def _payload(*, executes_live: bool = False, action: str = "add_negative_exact", confidence: str = "high", priority: str = "high", term: str = "waste term") -> dict:
    return {
        "recommendations": [
            {
                "entity_type": "search_term",
                "recommendation_type": action,
                "priority": priority,
                "confidence": confidence,
                "campaign_name": "Campaign A",
                "ad_group_name": "Group A",
                "targeting": 'keyword="waste"',
                "customer_search_term": term,
                "reasoning_summary": "Sufficient clicks and zero orders justify review.",
                "evidence": {
                    "metrics_used": {"clicks": 30, "spend": "35.00", "orders": 0},
                    "main_signals": ["30 clicks", "no orders"],
                    "risk_factors": [],
                    "data_limitations": [],
                },
                "proposed_action": {
                    "action": action,
                    "action_level": "search_term",
                    "suggested_bid_multiplier": None,
                    "negative_match_type": "exact" if action.startswith("add_negative") else None,
                    "requires_human_approval": True,
                    "executes_live_amazon_change": executes_live,
                },
            }
        ],
        "dashboard_summary": {
            "headline": "1 recommendation needs review.",
            "top_winners": [],
            "top_wasters": ["waste term"],
            "main_risks": [],
            "next_best_actions": [],
        },
    }


def test_retry_succeeds_after_first_attempt_fails_validation():
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    bad = _payload(executes_live=True)
    good = _payload(executes_live=False)
    client = _ScriptedClient([bad, good])
    brain = AiRecommendationBrain(client=client, max_attempts=3)

    result = brain.generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=rollups,
        data_quality_warnings=[],
    )

    assert result.used_ai is True
    assert result.attempts == 2
    assert len(result.recommendations) == 1
    assert len(client.calls) == 2
    # Second call must include the retry message with the prior errors.
    second_messages = client.calls[1]
    assert any("retry_after_validation_failure" in m["content"] for m in second_messages if isinstance(m.get("content"), str))


def test_retry_exhausts_after_repeated_failures():
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    bad = _payload(executes_live=True)
    client = _ScriptedClient([copy.deepcopy(bad), copy.deepcopy(bad), copy.deepcopy(bad)])
    brain = AiRecommendationBrain(client=client, max_attempts=3)

    result = brain.generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=rollups,
        data_quality_warnings=[],
    )

    assert result.used_ai is False
    assert result.attempts == 3
    assert len(client.calls) == 3
    assert result.ai_run.status == "failed"


def test_deterministic_confidence_overrides_llm_self_reported():
    product = _product()
    import_record = _import(product)
    # Very weak evidence — micro clicks, no spend — but the AI claims "high".
    snapshot = _snapshot(product, import_record, clicks=2, spend="0.50")
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    payload = _payload(executes_live=False, confidence="high")
    payload["recommendations"][0]["evidence"]["metrics_used"] = {"clicks": 2, "spend": "0.50", "orders": 0}
    client = _ScriptedClient([payload])
    brain = AiRecommendationBrain(client=client, max_attempts=1)

    result = brain.generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=rollups,
        data_quality_warnings=[],
    )

    # Critic might block this (clicks < 10 for negative); allow that path.
    assert result.used_ai is True
    if result.recommendations:
        rec = result.recommendations[0]
        # Deterministic confidence must NOT be high — too little evidence.
        assert rec.confidence in {
            RecommendationConfidence.VERY_LOW,
            RecommendationConfidence.LOW,
            RecommendationConfidence.MEDIUM,
        }
        assert rec.explanation_json["ai_self_reported_confidence"] == "high"
        assert rec.explanation_json["confidence_breakdown"]["confidence"] == rec.confidence.value


def test_critic_blocks_negative_on_converting_term_at_brain_level():
    product = _product()
    import_record = _import(product)
    # 3 orders — critic must block any negative on this.
    snapshot = _snapshot(product, import_record, clicks=40, orders=3, spend="60.00", sales="120.00")
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    client = _ScriptedClient([_payload(executes_live=False)])
    brain = AiRecommendationBrain(client=client, max_attempts=1)

    result = brain.generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=rollups,
        data_quality_warnings=[],
    )

    assert result.used_ai is True
    assert result.recommendations == []
    assert len(result.rejected_by_critic) == 1
    assert any(f["severity"] == "block" for f in result.critic_findings)


def test_pattern_memory_appears_in_prompt_and_explanation():
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    pattern_key = PatternKey(
        match_type="exact",
        acos_band="no_orders",
        click_volume_band="mid",
        action=RecommendationType.ADD_NEGATIVE_EXACT.value,
        strategy_mode="balanced",
    )
    pattern_index = {
        pattern_key_to_str(pattern_key): PatternOutcome(
            key=pattern_key,
            sample_size=10,
            median_acos_delta_pct=-20.0,
            median_spend_delta_pct=-40.0,
            success_rate=0.8,
            summary="action=add_negative_exact archetype=exact/no_orders/mid n=10 success_rate=80%",
        )
    }

    client = _ScriptedClient([_payload(executes_live=False)])
    brain = AiRecommendationBrain(client=client, max_attempts=1)

    result = brain.generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=rollups,
        data_quality_warnings=[],
        pattern_index=pattern_index,
        data_window_days=14,
    )

    # Pattern outcomes must appear in the prompt for the AI to read.
    user_msg = json.loads(client.calls[0][1]["content"])
    assert any(
        o.get("action") == RecommendationType.ADD_NEGATIVE_EXACT.value
        for o in user_msg["input"]["prior_pattern_outcomes"]
    )
    assert user_msg["input"]["data_window_days"] == 14

    # And the pattern outcome must be stamped on the surviving recommendation.
    if result.recommendations:
        rec = result.recommendations[0]
        assert rec.explanation_json["pattern_outcome"] is not None
        assert rec.explanation_json["pattern_outcome"]["sample_size"] == 10


def test_safety_invariants_still_hold_after_refactor():
    product = _product()
    import_record = _import(product)
    snapshot = _snapshot(product, import_record)
    rollups = monitoring_metrics.build_performance_rollups([snapshot])

    client = _ScriptedClient([_payload(executes_live=False)])
    brain = AiRecommendationBrain(client=client, max_attempts=1)

    result = brain.generate(
        product=product,
        import_record=import_record,
        snapshots=[snapshot],
        rollups=rollups,
        data_quality_warnings=[],
    )

    assert result.recommendations
    rec = result.recommendations[0]
    assert rec.proposed_action_json["executes_live_amazon_change"] is False
    assert rec.proposed_action_json["requires_human_approval"] is True
    assert rec.status.value == "pending_approval"
    assert rec.evidence_json["approval_boundary"]["requires_human_approval"] is True
    assert rec.explanation_json["execution_boundary"] == "recommendation_only_no_live_amazon_change"
