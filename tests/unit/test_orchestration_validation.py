from apps.api.app.orchestration.validation import validate_recommendation_payload


def test_validation_rejects_unsafe_ai_recommendation_thresholds() -> None:
    recommendation = {
        "entity_key": "search-term:1",
        "recommendation_type": "add_negative_exact",
        "confidence": "medium",
        "approval_required": True,
        "executes_live_amazon_change": False,
        "evidence": {"clicks": 2, "spend": "3.00"},
        "reasoning_summary": "Spend exists but evidence is below configured safety thresholds.",
        "proposed_action": {"requires_human_approval": True, "executes_live_amazon_change": False},
    }

    valid, errors = validate_recommendation_payload(
        recommendation=recommendation,
        grouped_entity_keys={"search-term:1"},
        agent_config={
            "allow_negative_exact": True,
            "confidence_threshold": "high",
            "require_high_confidence_for_negative_keywords": True,
            "require_min_clicks_before_action": 10,
            "require_min_spend_before_action": "10.00",
        },
    )

    assert valid is False
    assert "negative keyword recommendations require high confidence" in errors
    assert "recommendation does not meet minimum click threshold" in errors
    assert "recommendation does not meet minimum spend threshold" in errors


def test_validation_accepts_approval_only_recommendation_with_evidence() -> None:
    recommendation = {
        "entity_key": "search-term:1",
        "recommendation_type": "add_negative_exact",
        "confidence": "high",
        "approval_required": True,
        "executes_live_amazon_change": False,
        "evidence": {"metrics_used": {"clicks": 14, "spend": "22.50"}},
        "reasoning_summary": "High spend and clicks with no orders; review as a negative exact.",
        "proposed_action": {"requires_human_approval": True, "executes_live_amazon_change": False},
    }

    valid, errors = validate_recommendation_payload(
        recommendation=recommendation,
        grouped_entity_keys={"search-term:1"},
        agent_config={
            "allow_negative_exact": True,
            "confidence_threshold": "medium",
            "require_high_confidence_for_negative_keywords": True,
            "require_min_clicks_before_action": 10,
            "require_min_spend_before_action": "10.00",
        },
    )

    assert valid is True
    assert errors == []
