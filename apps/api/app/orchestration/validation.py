from decimal import Decimal, InvalidOperation


LIVE_CHANGE_WORDS = (
    "changed live",
    "updated live",
    "paused campaign",
    "bid changed",
    "negative keyword added",
    "executed in amazon ads",
)


def validate_recommendation_payload(*, recommendation: dict, grouped_entity_keys: set[str], agent_config: dict | None = None) -> tuple[bool, list[str]]:
    config = agent_config or {}
    errors: list[str] = []
    recommendation_type = str(recommendation.get("recommendation_type") or recommendation.get("type") or "")
    entity_key = str(recommendation.get("entity_key") or "")

    if not recommendation_type:
        errors.append("recommendation_type is required")
    if entity_key and grouped_entity_keys and entity_key not in grouped_entity_keys:
        errors.append("entity_key does not exist in grouped metrics")
    if recommendation.get("approval_required") is not True and recommendation.get("requires_human_approval") is not True:
        errors.append("approval_required must be true")
    if recommendation.get("executes_live_amazon_change") is not False:
        errors.append("executes_live_amazon_change must be false")
    if not recommendation.get("evidence"):
        errors.append("evidence is required")
    if not recommendation.get("reasoning_summary") and not recommendation.get("reasoning"):
        errors.append("reasoning_summary is required")

    allowed = _allowed_recommendation_types(config)
    if allowed and recommendation_type not in allowed:
        errors.append("recommendation type is disabled by agent config")

    confidence = str(recommendation.get("confidence") or "medium").lower()
    if _confidence_rank(confidence) < _confidence_rank(str(config.get("confidence_threshold") or "low")):
        errors.append("confidence below configured threshold")

    proposed_action = recommendation.get("proposed_action") or {}
    multiplier = _decimal_or_none(proposed_action.get("bid_multiplier"))
    if multiplier is not None:
        max_increase = _decimal_or_none(config.get("max_bid_increase_multiplier")) or Decimal("2")
        min_decrease = _decimal_or_none(config.get("max_bid_decrease_multiplier")) or Decimal("0.5")
        if multiplier > max_increase:
            errors.append("bid increase multiplier exceeds configured maximum")
        if multiplier < min_decrease:
            errors.append("bid decrease multiplier exceeds configured maximum")

    joined_text = " ".join(str(value).lower() for value in recommendation.values() if isinstance(value, str))
    if any(word in joined_text for word in LIVE_CHANGE_WORDS):
        errors.append("recommendation text claims a live Amazon Ads change occurred")

    return not errors, errors


def _allowed_recommendation_types(config: dict) -> set[str]:
    mapping = {
        "allow_keep_running": "keep_running",
        "allow_increase_bid": "increase_bid",
        "allow_decrease_bid": "decrease_bid",
        "allow_pause_review": "pause_review",
        "allow_negative_exact": "add_negative_exact",
        "allow_negative_phrase": "add_negative_phrase",
        "allow_move_to_exact": "move_to_exact",
        "allow_budget_review": "budget_review",
        "allow_data_quality_review": "data_quality_review",
    }
    if not any(key in config for key in mapping):
        return set()
    return {value for key, value in mapping.items() if config.get(key) is not False}


def _confidence_rank(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value.lower(), 1)


def _decimal_or_none(value) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
