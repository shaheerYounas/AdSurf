"""Risk & Policy Validator Agent for AdSurf.

This validator is the safety gate before any recommendation reaches
human approval. It rejects unsafe actions based on deterministic rules.

Rejects:
- Bid increase above max percentage
- Budget increase above allowed limit
- Negative keyword on a converting term
- Pause recommendation with too little data
- Duplicate bulk action
- Conflicting actions on same target
- Recommendation without evidence
- Recommendation based on low sample size
- Recommendation that violates selected strategy
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from apps.api.app.schemas.account_strategy import DEFAULT_STRATEGY_CONFIG, StrategyMode
from apps.api.app.schemas.monitoring import (
    EvidenceQuality,
    EvidenceScore,
    Recommendation,
    RecommendationConfidence,
    RecommendationType,
)
from apps.api.app.services.statistical_significance import (
    evaluate_recommendation_significance,
    evidence_strength_label,
)


class ValidationResult:
    def __init__(self, is_valid: bool, errors: list[str], warnings: list[str], risk_level: str):
        self.is_valid = is_valid
        self.errors = errors
        self.warnings = warnings
        self.risk_level = risk_level  # high, medium, low, none


def validate_recommendation(
    recommendation: Recommendation,
    *,
    strategy_mode: str = "profit",
    max_bid_increase_pct: float = 20.0,
    max_bid_decrease_pct: float = 50.0,
    max_budget_increase_pct: float = 30.0,
    allow_negative_keywords: bool = True,
    allow_auto_pause: bool = False,
    all_recommendations: list[Recommendation] | None = None,
) -> ValidationResult:
    """Validate a single recommendation against all safety rules.

    Returns ValidationResult with is_valid, errors, warnings, and risk_level.
    """
    errors: list[str] = []
    warnings: list[str] = []
    risk_level = "low"

    strategy_config = DEFAULT_STRATEGY_CONFIG.get(StrategyMode(strategy_mode), DEFAULT_STRATEGY_CONFIG[StrategyMode.PROFIT])
    effective_allow_negative_keywords = allow_negative_keywords and bool(strategy_config.get("allow_negative_keywords", True))

    # 1. Evidence check
    evidence_result = _validate_evidence(recommendation)
    errors.extend(evidence_result.errors)
    warnings.extend(evidence_result.warnings)

    # 2. Strategy violation check
    strategy_result = _validate_strategy(
        recommendation,
        strategy_mode=strategy_mode,
        strategy_config=strategy_config,
        max_bid_increase_pct=max_bid_increase_pct,
        max_bid_decrease_pct=max_bid_decrease_pct,
        max_budget_increase_pct=max_budget_increase_pct,
        allow_negative_keywords=effective_allow_negative_keywords,
        allow_auto_pause=allow_auto_pause,
    )
    errors.extend(strategy_result.errors)
    warnings.extend(strategy_result.warnings)

    # 3. Bid limit check
    bid_result = _validate_bid_limits(
        recommendation,
        max_bid_increase_pct=max_bid_increase_pct,
        max_bid_decrease_pct=max_bid_decrease_pct,
    )
    errors.extend(bid_result.errors)
    warnings.extend(bid_result.warnings)

    # 4. Negative keyword safety check
    neg_result = _validate_negative_keyword_safety(recommendation, allow_negative_keywords=effective_allow_negative_keywords)
    errors.extend(neg_result.errors)

    # 5. Conflict detection (duplicates, conflicting actions)
    if all_recommendations:
        conflict_result = _validate_conflicts(recommendation, all_recommendations)
        errors.extend(conflict_result.errors)
        warnings.extend(conflict_result.warnings)

    # 6. Budget change safety
    budget_result = _validate_budget_change(recommendation, max_budget_increase_pct=max_budget_increase_pct)
    errors.extend(budget_result.errors)

    # Determine risk level
    if errors:
        risk_level = "high"
    elif warnings and any("critical" in w.lower() for w in warnings):
        risk_level = "medium"
    elif warnings:
        risk_level = "low"
    else:
        risk_level = "none"

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        risk_level=risk_level,
    )


def validate_bulk_recommendations(
    recommendations: list[Recommendation],
    *,
    strategy_mode: str = "profit",
    max_bid_increase_pct: float = 20.0,
    max_bid_decrease_pct: float = 50.0,
    max_budget_increase_pct: float = 30.0,
    allow_negative_keywords: bool = True,
    allow_auto_pause: bool = False,
) -> dict[str, Any]:
    """Validate all recommendations in batch, detecting cross-recommendation conflicts.

    Returns dict with:
    - valid: list of valid recommendations
    - rejected: list of dicts with recommendation and validation errors
    - summary: dict with counts and risk distribution
    """
    valid: list[Recommendation] = []
    rejected: list[dict] = []

    for rec in recommendations:
        result = validate_recommendation(
            rec,
            strategy_mode=strategy_mode,
            max_bid_increase_pct=max_bid_increase_pct,
            max_bid_decrease_pct=max_bid_decrease_pct,
            max_budget_increase_pct=max_budget_increase_pct,
            allow_negative_keywords=allow_negative_keywords,
            allow_auto_pause=allow_auto_pause,
            all_recommendations=recommendations,
        )
        if result.is_valid:
            valid.append(rec)
        else:
            rejected.append({
                "recommendation": rec.model_dump(mode="json"),
                "validation_errors": result.errors,
                "warnings": result.warnings,
                "risk_level": result.risk_level,
            })

    risk_counts = defaultdict(int)
    for rec in valid:
        risk_counts[rec.risk_level or "none"] += 1
    for rejected_item in rejected:
        risk_counts[rejected_item["risk_level"]] += 1

    return {
        "valid": valid,
        "rejected": rejected,
        "summary": {
            "total": len(recommendations),
            "valid_count": len(valid),
            "rejected_count": len(rejected),
            "risk_distribution": dict(risk_counts),
            "high_risk_count": risk_counts.get("high", 0),
            "safe_for_export": len(valid) == len(recommendations) and risk_counts.get("high", 0) == 0,
        },
    }


def _validate_evidence(recommendation: Recommendation) -> ValidationResult:
    errors = []
    warnings = []

    metrics = recommendation.input_metrics_json
    clicks = int(metrics.get("clicks", 0))
    spend = float(metrics.get("spend", 0))
    orders = int(metrics.get("orders", 0))
    impressions = int(metrics.get("impressions", 0))

    evidence_score = recommendation.evidence_score

    # ── Wilson lower-bound statistical significance gate ──
    sig_report = evaluate_recommendation_significance(
        clicks=clicks,
        orders=orders,
        impressions=impressions,
        spend=spend,
        recommendation_type=str(recommendation.recommendation_type.value),
        z_score=1.96,
    )

    # Hard errors from significance checks
    errors.extend(sig_report.errors)

    # Warnings from significance checks
    warnings.extend(sig_report.warnings)

    # Evidence strength label (from Wilson + sample size)
    strength = evidence_strength_label(
        clicks=clicks,
        orders=orders,
        wilson_lower=sig_report.wilson_cvr_lower,
    )
    if strength == "very_weak":
        errors.append(f"Evidence strength is {strength}: only {clicks} clicks, {orders} orders. Cannot recommend action without more data.")
    elif strength == "weak":
        warnings.append(f"Evidence strength is {strength}: {clicks} clicks, {orders} orders. Recommendation is tentative and needs review.")
    elif strength == "strong":
        pass  # no warning needed for strong evidence

    if evidence_score and evidence_score.quality == EvidenceQuality.INSUFFICIENT:
        if recommendation.recommendation_type in {
            RecommendationType.PAUSE_KEYWORD,
            RecommendationType.PAUSE_TARGET,
            RecommendationType.PAUSE_REVIEW,
        }:
            errors.append("Cannot pause without sufficient evidence. Data sample is too small.")
        else:
            warnings.append("Recommendation based on insufficient data. Confidence is very low.")

    if evidence_score and evidence_score.quality == EvidenceQuality.WEAK:
        if clicks < 3 and spend > 0:
            warnings.append("Very few clicks. Recommendation confidence is weak.")

    if not metrics:
        errors.append("Recommendation must include metric evidence.")

    if orders == 0 and recommendation.recommendation_type in {
        RecommendationType.INCREASE_BID,
        RecommendationType.INCREASE_CAMPAIGN_BUDGET,
    }:
        if sig_report.wilson_cvr_lower < 0.01:
            warnings.append(f"Increasing bid without any order history is risky. Wilson CVR lower bound: {sig_report.wilson_cvr_lower:.4f}")

    # Include significance report in evidence
    if sig_report.requires_more_data:
        warnings.append(f"More data needed for statistical significance: clicks={clicks}/{sig_report.minimum_clicks_met}, spend={spend:.2f}/{sig_report.minimum_spend_met}")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        risk_level="high" if errors else "medium" if warnings else "low",
    )


def _validate_strategy(
    recommendation: Recommendation,
    *,
    strategy_mode: str,
    strategy_config: dict,
    max_bid_increase_pct: float,
    max_bid_decrease_pct: float,
    max_budget_increase_pct: float,
    allow_negative_keywords: bool,
    allow_auto_pause: bool,
) -> ValidationResult:
    errors = []
    warnings = []

    rec_type = recommendation.recommendation_type

    if str(rec_type).startswith("add_negative"):
        if not allow_negative_keywords:
            errors.append(f"Strategy '{strategy_mode}' prohibits negative keyword additions during launch/data gathering phase.")

    if rec_type in {RecommendationType.PAUSE_KEYWORD, RecommendationType.PAUSE_TARGET, RecommendationType.PAUSE_REVIEW}:
        if not allow_auto_pause:
            warnings.append("Auto-pause is disabled. Human approval is required for pauses.")

    if rec_type == RecommendationType.CREATE_EXACT_CAMPAIGN or rec_type == RecommendationType.CREATE_PRODUCT_TARGETING_CAMPAIGN:
        if not strategy_config.get("allow_new_campaign_creation", False):
            errors.append(f"Strategy '{strategy_mode}' does not allow automatic campaign creation.")

    # ACOS threshold check based on strategy
    if rec_type in {RecommendationType.DECREASE_BID, RecommendationType.PAUSE_REVIEW}:
        metrics = recommendation.input_metrics_json
        acos = float(metrics.get("acos", 0) or 0)
        acos_threshold = float(strategy_config.get("acos_multiplier_threshold", 1.25))
        if acos < 0.05 * acos_threshold:
            warnings.append("ACOS is very low. Consider whether this action might reduce profitable sales.")

    # ROAS minimum check
    if rec_type in {RecommendationType.DECREASE_BID, RecommendationType.PAUSE_REVIEW, RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        metrics = recommendation.input_metrics_json
        roas = float(metrics.get("roas", 0) or 0)
        roas_minimum = float(strategy_config.get("roas_minimum", 1.0))
        if roas > roas_minimum * 2:
            warnings.append(f"ROAS ({roas:.2f}) is well above minimum ({roas_minimum}). Verify this action doesn't harm strong performance.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, risk_level="high" if errors else "low")


def _validate_bid_limits(
    recommendation: Recommendation,
    *,
    max_bid_increase_pct: float,
    max_bid_decrease_pct: float,
) -> ValidationResult:
    errors = []
    warnings = []

    rec_type = recommendation.recommendation_type
    change_pct = float(recommendation.change_percent) if recommendation.change_percent else None

    if rec_type in {RecommendationType.INCREASE_BID, RecommendationType.SET_BID}:
        if change_pct is not None and change_pct > max_bid_increase_pct:
            errors.append(f"Bid increase {abs(change_pct):.0f}% exceeds maximum allowed {max_bid_increase_pct:.0f}%.")

    if rec_type == RecommendationType.DECREASE_BID:
        if change_pct is not None and abs(change_pct) > max_bid_decrease_pct:
            errors.append(f"Bid decrease {abs(change_pct):.0f}% exceeds maximum allowed {max_bid_decrease_pct:.0f}%.")

    if recommendation.current_bid is not None and recommendation.recommended_bid is not None:
        if recommendation.recommended_bid <= 0:
            errors.append("Recommended bid must be positive.")
        if recommendation.recommended_bid > recommendation.current_bid * Decimal("3"):
            warnings.append("Recommended bid is more than 3x the current bid. Verify this is intentional.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, risk_level="high" if errors else "low")


def _validate_negative_keyword_safety(recommendation: Recommendation, *, allow_negative_keywords: bool) -> ValidationResult:
    errors = []

    if str(recommendation.recommendation_type).startswith("add_negative"):
        if not allow_negative_keywords:
            errors.append("Negative keyword additions are disabled by strategy configuration.")

        metrics = recommendation.input_metrics_json
        orders = int(metrics.get("orders", 0))
        sales = float(metrics.get("sales", 0))

        if orders > 0:
            errors.append(f"Cannot add negative keyword on converting term. This term has {orders} orders and ${sales:.2f} sales.")

        clicks = int(metrics.get("clicks", 0))
        if clicks < 10:
            errors.append("Cannot add negative keyword with less than 10 clicks. Insufficient data to classify as waste.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=[], risk_level="high" if errors else "none")


def _validate_conflicts(
    recommendation: Recommendation,
    all_recommendations: list[Recommendation],
) -> ValidationResult:
    errors = []
    warnings = []

    rec_id = str(recommendation.id)
    rec_type = recommendation.recommendation_type
    rec_key = _entity_key(recommendation)

    for other in all_recommendations:
        if str(other.id) == rec_id:
            continue

        other_key = _entity_key(other)
        if rec_key != other_key:
            continue

        # Detect duplicate actions on same entity
        if recommendation.recommendation_type == other.recommendation_type:
            warnings.append(f"Duplicate action '{rec_type.value}' on entity '{rec_key}'.")

        # Detect conflicting actions
        conflicts = {
            (RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID),
            (RecommendationType.INCREASE_BID, RecommendationType.PAUSE_KEYWORD),
            (RecommendationType.INCREASE_BID, RecommendationType.PAUSE_TARGET),
            (RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.HARVEST_TO_EXACT),
            (RecommendationType.ADD_NEGATIVE_PHRASE, RecommendationType.HARVEST_TO_PHRASE),
            (RecommendationType.INCREASE_CAMPAIGN_BUDGET, RecommendationType.DECREASE_CAMPAIGN_BUDGET),
        }

        pair = {rec_type, other.recommendation_type}
        if frozenset(pair) in {frozenset(c) for c in conflicts}:
            errors.append(f"Conflicting actions '{rec_type.value}' and '{other.recommendation_type.value}' on entity '{rec_key}'.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, risk_level="high" if errors else "low")


def _validate_budget_change(recommendation: Recommendation, *, max_budget_increase_pct: float) -> ValidationResult:
    errors = []

    if recommendation.recommendation_type in {
        RecommendationType.INCREASE_CAMPAIGN_BUDGET,
        RecommendationType.MOVE_BUDGET_TO_PROFITABLE,
    }:
        if recommendation.current_budget is not None and recommendation.recommended_budget is not None:
            change_pct = float(
                (recommendation.recommended_budget - recommendation.current_budget)
                / recommendation.current_budget
                * 100
            )
            if change_pct > max_budget_increase_pct:
                errors.append(f"Budget increase {change_pct:.0f}% exceeds maximum allowed {max_budget_increase_pct:.0f}%.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=[], risk_level="high" if errors else "medium")


def _entity_key(recommendation: Recommendation) -> str:
    parts = [
        recommendation.campaign_name or "",
        recommendation.ad_group_name or "",
        recommendation.targeting or "",
        recommendation.customer_search_term or "",
    ]
    return "|".join(parts).strip("|")
