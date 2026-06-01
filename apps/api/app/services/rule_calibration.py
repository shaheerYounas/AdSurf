"""Closed-Loop Rule Calibration Service for AdSurf.

Consumes outcome data from learning_feedback_agent and adjusts
deterministic rule thresholds within bounded ranges (±20% of original).
This is the feedback loop that turns learning_feedback from
"reporting" into "learning."

Architecture:
    learning_feedback.analyze_outcomes()
        → rule_effectiveness scores per rule
        → calibration_service.adjust_rule_thresholds()
            → rule_calibration table (bounded ±20% adjustments)
            → next run's deterministic thresholds use calibrated values

This runs as a nightly job (or on-demand after analysis cycles).
It NEVER adjusts thresholds outside ±20% of the original value.
It NEVER applies adjustments without at least 5 observations per rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any
from uuid import UUID


# ── Default rule parameter definitions ──────────────────────────────────
# Each parameter has an original value and allowed bounds (±20%)

@dataclass(frozen=True)
class RuleParameter:
    """Definition of a calibratable rule parameter."""

    rule_name: str
    parameter: str
    original_value: float
    description: str

    @property
    def bounded_min(self) -> float:
        return self.original_value * 0.80

    @property
    def bounded_max(self) -> float:
        return self.original_value * 1.20


# The set of parameters that can be auto-calibrated
CALIBRATABLE_PARAMETERS: list[RuleParameter] = [
    RuleParameter("negative_keyword_rule", "min_clicks_for_negative", 10.0,
                  "Minimum clicks before a search term can be flagged as negative"),
    RuleParameter("negative_keyword_rule", "min_spend_for_negative", 5.0,
                  "Minimum spend before a search term can be flagged as negative"),
    RuleParameter("bid_optimization_rule", "max_bid_increase_pct", 20.0,
                  "Maximum allowed bid increase percentage"),
    RuleParameter("bid_optimization_rule", "max_bid_decrease_pct", 50.0,
                  "Maximum allowed bid decrease percentage"),
    RuleParameter("pause_review_rule", "min_clicks_for_pause", 15.0,
                  "Minimum clicks before pause review is triggered"),
    RuleParameter("pause_review_rule", "min_spend_for_pause", 10.0,
                  "Minimum spend before pause review is triggered"),
    RuleParameter("budget_reallocation_rule", "max_budget_increase_pct", 30.0,
                  "Maximum allowed budget increase percentage"),
    RuleParameter("harvest_rule", "min_orders_for_harvest", 1.0,
                  "Minimum orders before search term can be harvested to exact"),
    RuleParameter("harvest_rule", "min_sales_for_harvest", 10.0,
                  "Minimum sales amount before harvest"),
    RuleParameter("evidence_rule", "min_clicks_for_evidence", 5.0,
                  "Minimum clicks to consider evidence adequate"),
    RuleParameter("evidence_rule", "min_orders_for_evidence", 0.0,
                  "Minimum orders to consider evidence adequate"),
]


PARAMETER_LOOKUP: dict[tuple[str, str], RuleParameter] = {
    (p.rule_name, p.parameter): p for p in CALIBRATABLE_PARAMETERS
}


@dataclass
class CalibrationResult:
    """Result of a calibration run."""

    workspace_id: str
    parameters_adjusted: int = 0
    parameters_unchanged: int = 0
    parameters_skipped: int = 0
    adjustments: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def calibrate_rules_from_feedback(
    *,
    workspace_id: UUID,
    feedback_results: dict[str, Any],
    product_id: UUID | None = None,
    min_observations: int = 5,
    max_adjustment_per_cycle: float = 5.0,
) -> CalibrationResult:
    """Generate rule calibration adjustments from learning feedback outcomes.

    Args:
        workspace_id: Current workspace
        feedback_results: Output of learning_feedback.analyze_outcomes()
        product_id: Optional product scoping
        min_observations: Minimum decisions per rule before calibration
        max_adjustment_per_cycle: Maximum percentage shift per cycle

    Returns:
        CalibrationResult with list of adjustments to persist
    """
    result = CalibrationResult(workspace_id=str(workspace_id))

    rule_scores = feedback_results.get("rule_effectiveness", {})
    if not rule_scores:
        result.summary = "No rule effectiveness data in feedback results. Skipping calibration."
        return result

    for rule_name, scores in rule_scores.items():
        total = scores.get("total_decisions", scores.get("total", 0))
        accuracy = scores.get("accuracy", 0.0)
        correct = scores.get("correct", 0)
        incorrect = scores.get("incorrect", 0)

        if total < min_observations:
            result.parameters_skipped += 1
            continue

        for (r_name, param), defn in PARAMETER_LOOKUP.items():
            if r_name != rule_name and not rule_name.startswith(r_name):
                continue

            adjustment = _calculate_adjustment(
                current_value=defn.original_value,
                accuracy=accuracy,
                total_decisions=total,
                correct=correct,
                incorrect=incorrect,
                bounded_min=defn.bounded_min,
                bounded_max=defn.bounded_max,
                max_adjustment_per_cycle=max_adjustment_per_cycle,
            )

            if abs(adjustment.adjustment_pct) < 0.1:
                result.parameters_unchanged += 1
                continue

            result.adjustments.append({
                "rule_name": rule_name,
                "parameter": param,
                "original_value": defn.original_value,
                "current_value": adjustment.new_value,
                "adjustment_pct": adjustment.adjustment_pct,
                "bounded_min": defn.bounded_min,
                "bounded_max": defn.bounded_max,
                "evidence": {
                    "accuracy": accuracy,
                    "total_decisions": total,
                    "correct": correct,
                    "incorrect": incorrect,
                },
                "product_id": str(product_id) if product_id else None,
            })
            result.parameters_adjusted += 1

    result.summary = (
        f"Calibrated {result.parameters_adjusted} parameters across "
        f"{len(rule_scores)} rules. {result.parameters_unchanged} unchanged, "
        f"{result.parameters_skipped} skipped (insufficient data)."
    )
    return result


@dataclass(frozen=True)
class _Adjustment:
    adjustment_pct: float
    new_value: float


def _calculate_adjustment(
    *,
    current_value: float,
    accuracy: float,
    total_decisions: int,
    correct: int,
    incorrect: int,
    bounded_min: float,
    bounded_max: float,
    max_adjustment_per_cycle: float = 5.0,
) -> _Adjustment:
    """Calculate the adjustment for a single rule parameter.

    Strategy:
    - If accuracy > 85%: tighten parameter slightly
    - If accuracy < 50%: loosen parameter
    - If accuracy 50-85%: no change
    - All adjustments capped at ±max_adjustment_per_cycle and within bounds
    """
    if accuracy < 0.50 and total_decisions >= 10:
        direction = -1.0
    elif accuracy > 0.85 and total_decisions >= 10:
        direction = 1.0
    else:
        return _Adjustment(adjustment_pct=0.0, new_value=current_value)

    accuracy_distance = abs(accuracy - 0.70)
    observation_weight = min(total_decisions / 20.0, 1.0)
    base_adjustment_pct = accuracy_distance * 10.0 * observation_weight
    adjustment_pct = min(base_adjustment_pct, max_adjustment_per_cycle) * direction
    new_value = current_value * (1.0 + adjustment_pct / 100.0)

    if new_value > bounded_max:
        new_value = bounded_max
    elif new_value < bounded_min:
        new_value = bounded_min

    effective_adjustment_pct = ((new_value - current_value) / current_value) * 100.0

    return _Adjustment(
        adjustment_pct=round(effective_adjustment_pct, 2),
        new_value=round(new_value, 2),
    )


def get_calibrated_value(
    *,
    rule_name: str,
    parameter: str,
    current_calibrations: dict[str, float] | None = None,
    fallback_original: float | None = None,
) -> float:
    """Look up the current calibrated value for a rule parameter."""
    calibrations = current_calibrations or {}
    key = f"{rule_name}:{parameter}"
    if key in calibrations:
        return calibrations[key]
    defn = PARAMETER_LOOKUP.get((rule_name, parameter))
    if defn:
        return defn.original_value
    if fallback_original is not None:
        return fallback_original
    raise KeyError(f"No parameter definition for {rule_name}:{parameter}")