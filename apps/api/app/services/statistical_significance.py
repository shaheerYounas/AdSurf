"""Statistical significance gates for AdSurf recommendation validation.

Provides Wilson lower-bound confidence intervals for conversion rates,
minimum sample-size checks, and Spend-per-Order threshold gating.
These are deterministic, math-only checks — no AI involved.

Used by risk_validator to add a Bayesian evidence-quality dimension
beyond simple click-count thresholds.

Wilson score interval reference:
    Wilson, E.B. (1927). "Probable inference, the law of succession,
    and statistical inference." Journal of the American Statistical
    Association, 22(158), 209-212.

Implementation follows the standard formula:
    lower = (p + z²/(2n) - z*sqrt(p(1-p)/n + z²/(4n²))) / (1 + z²/n)
    where p = conversions/impressions, n = impressions, z = z-score
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


# ── Core Wilson functions ────────────────────────────────────────────────


def wilson_lower_bound(
    successes: int,
    trials: int,
    z: float = 1.96,  # 95% confidence
) -> float:
    """Wilson score interval lower bound for a binomial proportion.

    Args:
        successes: Number of conversions (orders, purchases)
        trials: Number of trials (clicks, impressions)
        z: z-score for confidence level (1.96 = 95%, 2.576 = 99%)

    Returns:
        Lower bound of the true conversion rate with given confidence.
        Returns 0.0 when trials=0.
    """
    if trials <= 0:
        return 0.0
    if successes < 0:
        successes = 0
    if successes > trials:
        successes = trials

    p = successes / trials
    n = trials
    z2 = z * z

    denominator = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))

    lower = (center - margin) / denominator
    return max(0.0, lower)


def wilson_upper_bound(
    successes: int,
    trials: int,
    z: float = 1.96,
) -> float:
    """Wilson score interval upper bound."""
    if trials <= 0:
        return 1.0
    if successes < 0:
        successes = 0
    if successes > trials:
        successes = trials

    p = successes / trials
    n = trials
    z2 = z * z

    denominator = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))

    upper = (center + margin) / denominator
    return min(1.0, upper)


# ── Ad-specific significance checks ─────────────────────────────────────


@dataclass(frozen=True)
class SignificanceCheck:
    """Result of a single statistical significance check."""

    name: str
    passed: bool
    value: float
    threshold: float
    detail: str = ""
    is_warning: bool = False  # if True, failure generates a warning not an error


@dataclass
class SignificanceReport:
    """Aggregated significance check results for a recommendation candidate."""

    checks: list[SignificanceCheck] = field(default_factory=list)
    overall_passed: bool = True
    requires_more_data: bool = False
    wilson_cvr_lower: float = 0.0
    wilson_cvr_upper: float = 0.0
    minimum_clicks_met: bool = True
    minimum_spend_met: bool = True
    minimum_orders_met: bool = True

    @property
    def errors(self) -> list[str]:
        return [c.detail for c in self.checks if not c.passed and not c.is_warning]

    @property
    def warnings(self) -> list[str]:
        return [c.detail for c in self.checks if not c.passed and c.is_warning]


def evaluate_recommendation_significance(
    *,
    clicks: int,
    orders: int,
    impressions: int,
    spend: float | Decimal,
    recommendation_type: str,
    target_acos: float | Decimal | None = None,
    z_score: float = 1.96,
) -> SignificanceReport:
    """Evaluate whether a recommendation has sufficient data to be statistically meaningful.

    Performs multiple checks:
    1. Minimum clicks before any action (10 for most, 15 for pause/negative)
    2. Wilson lower-bound CVR for bid increase decisions
    3. Minimum spend for budget recommendations
    4. Minimum orders for scaling recommendations
    5. Spend significance for negative keyword decisions

    Args:
        clicks: Total clicks in the period
        orders: Total orders in the period
        impressions: Total impressions in the period
        spend: Total spend in the period
        recommendation_type: The type of recommendation being evaluated
        target_acos: Target ACOS for the product (used for spend-gating)
        z_score: z-score (1.96 = 95% confidence; use 2.576 for 99%)

    Returns:
        SignificanceReport with pass/fail for each check.
    """
    spend_val = float(spend) if isinstance(spend, Decimal) else float(spend or 0)
    report = SignificanceReport()

    # 1. Wilson lower-bound CVR
    cvr_lower = wilson_lower_bound(orders, clicks, z=z_score)
    cvr_upper = wilson_upper_bound(orders, clicks, z=z_score)
    report.wilson_cvr_lower = cvr_lower
    report.wilson_cvr_upper = cvr_upper

    # 2. Minimum clicks check
    min_clicks = _min_clicks_threshold(recommendation_type)
    clicks_ok = clicks >= min_clicks
    report.minimum_clicks_met = clicks_ok
    report.checks.append(
        SignificanceCheck(
            name="minimum_clicks",
            passed=clicks_ok,
            value=clicks,
            threshold=min_clicks,
            detail=f"Required {min_clicks} clicks for {recommendation_type}; observed {clicks}." if not clicks_ok else "",
            is_warning=clicks >= min_clicks * 0.5,  # borderline is a warning
        )
    )

    # 3. Minimum spend check
    min_spend = _min_spend_threshold(recommendation_type)
    spend_ok = spend_val >= min_spend
    report.minimum_spend_met = spend_ok
    report.checks.append(
        SignificanceCheck(
            name="minimum_spend",
            passed=spend_ok,
            value=spend_val,
            threshold=min_spend,
            detail=f"Required ${min_spend:.2f} spend for {recommendation_type}; observed ${spend_val:.2f}." if not spend_ok else "",
            is_warning=False,
        )
    )

    # 4. Minimum orders for scaling/positive decisions
    min_orders = _min_orders_threshold(recommendation_type)
    orders_ok = orders >= min_orders
    report.minimum_orders_met = orders_ok
    if min_orders > 0:
        report.checks.append(
            SignificanceCheck(
                name="minimum_orders",
                passed=orders_ok,
                value=orders,
                threshold=min_orders,
                detail=f"Required {min_orders} orders for {recommendation_type}; observed {orders}." if not orders_ok else "",
                is_warning=recommendation_type in {"increase_bid", "harvest_to_exact", "move_to_exact", "budget_review"},
            )
        )

    # 5. Wilson CVR significance for bid-increase decisions
    if recommendation_type == "increase_bid":
        # Require at least 1% CVR lower bound to justify increasing bid
        cvr_threshold = 0.01
        cvr_ok = cvr_lower >= cvr_threshold
        report.checks.append(
            SignificanceCheck(
                name="wilson_cvr_for_bid_increase",
                passed=cvr_ok,
                value=cvr_lower,
                threshold=cvr_threshold,
                detail=f"Wilson lower-bound CVR {cvr_lower:.4f} below {cvr_threshold} for bid increase." if not cvr_ok else "",
                is_warning=True,  # CVR alone shouldn't block; it's a guidance signal
            )
        )

    # 6. For negative keywords — require statistically significant waste
    if recommendation_type in {"add_negative_exact", "add_negative_phrase"}:
        if orders == 0 and clicks >= min_clicks:
            # Zero orders with enough clicks — this IS statistically significant waste
            report.checks.append(
                SignificanceCheck(
                    name="zero_conversion_waste",
                    passed=True,
                    value=0,
                    threshold=0,
                    detail=f"Zero orders on {clicks} clicks — statistically significant waste.",
                )
            )
        elif orders > 0:
            # Has orders, so NOT waste
            report.checks.append(
                SignificanceCheck(
                    name="not_waste_has_orders",
                    passed=False,
                    value=orders,
                    threshold=0,
                    detail=f"Cannot mark as negative: {orders} orders observed.",
                    is_warning=False,
                )
            )
            report.overall_passed = False

    # 7. For pause recommendations — require clear evidence of underperformance
    if recommendation_type in {"pause_review", "pause_keyword", "pause_target"}:
        if clicks >= min_clicks and orders == 0 and spend_val >= min_spend:
            report.checks.append(
                SignificanceCheck(
                    name="pause_evidence_sufficient",
                    passed=True,
                    value=clicks,
                    threshold=min_clicks,
                    detail=f"Sufficient evidence for pause: {clicks} clicks, 0 orders, ${spend_val:.2f} spent.",
                )
            )
        elif clicks < min_clicks:
            report.checks.append(
                SignificanceCheck(
                    name="pause_insufficient_clicks",
                    passed=False,
                    value=clicks,
                    threshold=min_clicks,
                    detail=f"Insufficient clicks ({clicks}) to justify pause. Need at least {min_clicks}.",
                    is_warning=False,
                )
            )
            report.overall_passed = False

    # 8. Overall requires-more-data flag
    if not clicks_ok or not spend_ok:
        report.requires_more_data = True

    # Overall pass: no hard-failing (non-warning) checks
    hard_failures = [c for c in report.checks if not c.passed and not c.is_warning]
    report.overall_passed = len(hard_failures) == 0

    return report


def _min_clicks_threshold(recommendation_type: str) -> int:
    """Minimum clicks required before taking action."""
    high_threshold = {"pause_review", "pause_keyword", "pause_target"}
    medium_threshold = {"decrease_bid", "add_negative_exact", "add_negative_phrase"}
    if recommendation_type in high_threshold:
        return 15
    if recommendation_type in medium_threshold:
        return 10
    return 5  # increase_bid, harvest, move, structure changes


def _min_spend_threshold(recommendation_type: str) -> float:
    """Minimum spend required before taking action."""
    high_threshold = {"increase_campaign_budget", "budget_review", "move_budget_to_profitable"}
    medium_threshold = {"pause_review", "pause_keyword", "pause_target", "add_negative_exact", "add_negative_phrase"}
    if recommendation_type in high_threshold:
        return 20.0
    if recommendation_type in medium_threshold:
        return 5.0
    return 1.0


def _min_orders_threshold(recommendation_type: str) -> int:
    """Minimum orders required for scaling/positive decisions."""
    scaling_types = {"increase_bid", "harvest_to_exact", "move_to_exact", "budget_review"}
    if recommendation_type in scaling_types:
        return 1
    return 0


# ── Utility: confidence-based gating ────────────────────────────────────


def evidence_strength_label(
    *,
    clicks: int,
    orders: int,
    wilson_lower: float,
) -> str:
    """Human-readable evidence strength label."""
    if clicks < 5:
        return "very_weak"
    if clicks < 15:
        if orders == 0:
            return "weak"
        return "moderate"
    if clicks < 50:
        if orders >= 3:
            return "strong"
        if orders >= 1:
            return "moderate"
        if wilson_lower >= 0.005:
            return "moderate"
        return "weak"
    if clicks >= 100 and orders >= 5 and wilson_lower >= 0.01:
        return "very_strong"
    if orders >= 1:
        return "strong"
    return "moderate"
