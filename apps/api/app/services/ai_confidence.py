"""Deterministic confidence calculator for AI recommendations.

The LLM's self-reported `confidence` field is unreliable — it reflects the
model's verbal certainty, not the strength of the underlying evidence. This
module computes confidence from observable signals (click volume, spend, days
of data, prior-recommendation outcomes for the same archetype) and overrides
whatever the model returned.

Inputs are deterministic; the LLM only contributes the *explanation* of why a
recommendation was selected, not the confidence score driving prioritization.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    RecommendationConfidence,
    RecommendationType,
)


# Tiered click volume thresholds — each tier represents a step-change in the
# statistical reliability of click-based metrics like CVR and CPC.
_CLICK_TIER_VERY_HIGH = 50
_CLICK_TIER_HIGH = 20
_CLICK_TIER_MEDIUM = 10
_CLICK_TIER_LOW = 3

# Spend tiers in account currency. Recommendations on cents-of-spend lines are
# noise; recommendations on $50+ lines are decisions worth defending.
_SPEND_TIER_VERY_HIGH = Decimal("50.00")
_SPEND_TIER_HIGH = Decimal("20.00")
_SPEND_TIER_MEDIUM = Decimal("5.00")

# Data window in days. Single-day reports are anecdotes; 14d+ is signal.
_DAYS_TIER_VERY_HIGH = 14
_DAYS_TIER_HIGH = 7
_DAYS_TIER_MEDIUM = 3


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Trace of how a confidence score was computed. Stored on the
    recommendation so reviewers can see the math, not just the verdict."""

    confidence: RecommendationConfidence
    score: int
    components: dict[str, int]
    notes: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence.value,
            "score": self.score,
            "components": dict(self.components),
            "notes": list(self.notes),
            "method": "deterministic_evidence_weighted_v1",
        }


def compute_confidence(
    *,
    snapshot: MonitoringSnapshot,
    recommendation_type: RecommendationType,
    data_window_days: int | None = None,
    pattern_outcome: dict[str, Any] | None = None,
) -> ConfidenceBreakdown:
    """Score recommendation confidence from evidence, ignoring LLM self-rating.

    Score range is 0-100, mapped to RecommendationConfidence tiers:
        >= 85 very_high, >= 65 high, >= 45 medium, >= 25 low, else very_low.

    `pattern_outcome` is the optional record from the optimization memory for
    this archetype × action; if past attempts of the same kind worked, we add
    weight, and if they failed, we subtract.
    """

    components: dict[str, int] = {}
    notes: list[str] = []

    components["click_volume"] = _click_volume_score(snapshot.clicks)
    components["spend_volume"] = _spend_volume_score(snapshot.spend)
    components["data_window"] = _data_window_score(data_window_days)
    components["action_specific"] = _action_specific_score(snapshot, recommendation_type, notes)
    components["pattern_history"] = _pattern_history_score(pattern_outcome, notes)

    score = sum(components.values())
    score = max(0, min(100, score))

    confidence = _score_to_confidence(score)

    return ConfidenceBreakdown(
        confidence=confidence,
        score=score,
        components=components,
        notes=notes,
    )


def _click_volume_score(clicks: int) -> int:
    if clicks >= _CLICK_TIER_VERY_HIGH:
        return 30
    if clicks >= _CLICK_TIER_HIGH:
        return 22
    if clicks >= _CLICK_TIER_MEDIUM:
        return 14
    if clicks >= _CLICK_TIER_LOW:
        return 6
    return 0


def _spend_volume_score(spend: Decimal) -> int:
    if spend >= _SPEND_TIER_VERY_HIGH:
        return 25
    if spend >= _SPEND_TIER_HIGH:
        return 18
    if spend >= _SPEND_TIER_MEDIUM:
        return 10
    if spend > 0:
        return 4
    return 0


def _data_window_score(days: int | None) -> int:
    if days is None:
        return 8
    if days >= _DAYS_TIER_VERY_HIGH:
        return 20
    if days >= _DAYS_TIER_HIGH:
        return 14
    if days >= _DAYS_TIER_MEDIUM:
        return 8
    return 2


def _action_specific_score(
    snapshot: MonitoringSnapshot,
    recommendation_type: RecommendationType,
    notes: list[str],
) -> int:
    """Some action types demand stronger evidence than others.

    A negative-keyword recommendation needs zero orders (and we want to be
    *more* sure when blocking a term than when nudging a bid). Bid-up needs
    converting evidence. We reward strong signals and penalize the weak ones.
    """

    score = 0
    rec = recommendation_type

    if rec in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        if snapshot.orders == 0 and snapshot.spend > 0 and snapshot.clicks >= _CLICK_TIER_HIGH:
            score += 15
            notes.append("Strong wasted-spend evidence: clicks above threshold and zero orders.")
        elif snapshot.orders > 0:
            score -= 25
            notes.append("Penalty: term has converting orders — negative is high-risk.")

    elif rec in {RecommendationType.INCREASE_BID, RecommendationType.MOVE_TO_EXACT}:
        if snapshot.orders >= 2 and snapshot.sales > 0:
            score += 12
            notes.append("Multiple orders support scaling.")
        elif snapshot.orders == 0:
            score -= 10
            notes.append("Penalty: scaling action with no order evidence.")

    elif rec == RecommendationType.DECREASE_BID:
        if snapshot.orders == 0 and snapshot.spend > 0:
            score += 10
            notes.append("Wasted-spend pattern supports controlled decrease.")

    elif rec == RecommendationType.PAUSE_REVIEW:
        if snapshot.clicks >= _CLICK_TIER_VERY_HIGH and snapshot.orders == 0:
            score += 10
            notes.append("High-click, zero-order pattern supports pause review.")
        else:
            score -= 8
            notes.append("Penalty: pause without overwhelming evidence.")

    return score


def _pattern_history_score(pattern_outcome: dict[str, Any] | None, notes: list[str]) -> int:
    if not pattern_outcome:
        return 0

    median_acos_delta = pattern_outcome.get("median_acos_delta_pct")
    sample_size = int(pattern_outcome.get("sample_size") or 0)

    if sample_size < 3:
        return 0

    weight = min(15, sample_size)

    if median_acos_delta is None:
        return 0

    try:
        delta = float(median_acos_delta)
    except (TypeError, ValueError):
        return 0

    if delta <= -10:
        notes.append(
            f"Past archetype outcome: ACOS improved by {abs(delta):.0f}% over n={sample_size}."
        )
        return weight
    if delta <= -3:
        notes.append(
            f"Past archetype outcome: modest ACOS improvement ({abs(delta):.0f}%, n={sample_size})."
        )
        return max(4, weight // 2)
    if delta >= 10:
        notes.append(
            f"Past archetype outcome: ACOS worsened by {delta:.0f}% (n={sample_size})."
        )
        return -weight
    if delta >= 3:
        notes.append(
            f"Past archetype outcome: slight ACOS regression ({delta:.0f}%, n={sample_size})."
        )
        return -max(4, weight // 2)
    return 0


def _score_to_confidence(score: int) -> RecommendationConfidence:
    if score >= 85:
        return RecommendationConfidence.VERY_HIGH
    if score >= 65:
        return RecommendationConfidence.HIGH
    if score >= 45:
        return RecommendationConfidence.MEDIUM
    if score >= 25:
        return RecommendationConfidence.LOW
    return RecommendationConfidence.VERY_LOW
