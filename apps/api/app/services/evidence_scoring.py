"""Evidence scoring system for AdSurf recommendations.

Confidence should depend on clicks, spend, orders, conversion volume,
days of data, and product lifecycle. Higher evidence = higher confidence.
"""

from decimal import Decimal

from apps.api.app.schemas.monitoring import (
    EvidenceQuality,
    EvidenceScore,
    MonitoringSnapshot,
)


MIN_CLICKS_STRONG = 30
MIN_CLICKS_ADEQUATE = 15
MIN_CLICKS_WEAK = 5
MIN_SPEND_STRONG = Decimal("50")
MIN_SPEND_ADEQUATE = Decimal("20")
MIN_SPEND_WEAK = Decimal("5")
MIN_ORDERS_STRONG = 10
MIN_ORDERS_ADEQUATE = 3
MIN_ORDERS_WEAK = 1
MIN_DAYS_STRONG = 30
MIN_DAYS_ADEQUATE = 14
MIN_DAYS_WEAK = 7


def score_evidence(
    snapshot: MonitoringSnapshot,
    *,
    days_of_data: int = 14,
    product_lifecycle_stage: str = "mature",
) -> EvidenceScore:
    """Score the quality of evidence for a given snapshot.

    Returns an EvidenceScore with component scores and overall quality rating.
    Higher scores mean more reliable evidence for decision-making.
    """
    clicks = snapshot.clicks
    spend = snapshot.spend
    orders = snapshot.orders

    clicks_score = _linear_score(clicks, MIN_CLICKS_STRONG, MIN_CLICKS_WEAK)
    spend_score = _linear_score(float(spend), float(MIN_SPEND_STRONG), float(MIN_SPEND_WEAK))
    orders_score = _linear_score(orders, MIN_ORDERS_STRONG, MIN_ORDERS_WEAK)
    days_score = _linear_score(days_of_data, MIN_DAYS_STRONG, MIN_DAYS_WEAK)

    cvr = float(snapshot.cvr) if snapshot.cvr is not None else 0.0
    conversion_score = _linear_score(
        orders,
        MIN_ORDERS_STRONG,
        MIN_ORDERS_WEAK,
    ) * 0.5 + (min(cvr, 0.2) / 0.2) * 0.5

    # Product lifecycle adjustment: new products need less data to be considered "adequate"
    if product_lifecycle_stage == "launch":
        lifecycle_multiplier = 1.5
    elif product_lifecycle_stage == "new":
        lifecycle_multiplier = 1.2
    else:
        lifecycle_multiplier = 1.0

    raw_overall = (
        clicks_score * 0.20
        + spend_score * 0.20
        + orders_score * 0.25
        + days_score * 0.15
        + conversion_score * 0.20
    )
    overall_score = min(raw_overall * lifecycle_multiplier, 1.0)

    if overall_score >= 0.80 and orders >= MIN_ORDERS_STRONG:
        quality = EvidenceQuality.STRONG
    elif overall_score >= 0.50 and orders >= MIN_ORDERS_ADEQUATE:
        quality = EvidenceQuality.ADEQUATE
    elif overall_score >= 0.25:
        quality = EvidenceQuality.WEAK
    else:
        quality = EvidenceQuality.INSUFFICIENT

    return EvidenceScore(
        quality=quality,
        clicks_score=clicks_score,
        spend_score=spend_score,
        orders_score=orders_score,
        days_score=days_score,
        conversion_score=conversion_score,
        overall_score=overall_score,
        sample_size_adequate=clicks >= MIN_CLICKS_ADEQUATE and days_of_data >= MIN_DAYS_ADEQUATE,
        sufficient_history=days_of_data >= MIN_DAYS_STRONG,
    )


def evidence_to_confidence(score: EvidenceScore) -> str:
    """Map evidence score to confidence level string."""
    mapping = {
        EvidenceQuality.STRONG: "very_high",
        EvidenceQuality.ADEQUATE: "high",
        EvidenceQuality.WEAK: "medium",
        EvidenceQuality.INSUFFICIENT: "low",
    }
    if score.overall_score < 0.15:
        return "very_low"
    if score.overall_score < 0.10:
        return "insufficient_data"
    return mapping.get(score.quality, "medium")


def _linear_score(value: float, max_threshold: float, min_threshold: float) -> float:
    """Linear score between 0 and 1 based on threshold range."""
    if max_threshold <= min_threshold:
        return 1.0 if value >= max_threshold else 0.0
    if value >= max_threshold:
        return 1.0
    if value <= min_threshold:
        return value / min_threshold * 0.2
    return 0.2 + 0.8 * (value - min_threshold) / (max_threshold - min_threshold)