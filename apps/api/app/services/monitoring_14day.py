"""Phase 3 Monitoring Backbone — 14-Day Observation Loop for AdSurf.

Implements the monitoring infrastructure that turns AdSurf from a
"recommendation reporter" into an "optimization system":

1. Daily snapshot ingestion with time-series tracking
2. Day-7 ACOS checkpoint (gate for bid adjustments)
3. Campaign-lock state machine (prevent conflicting changes within lock window)
4. 14-day closed-loop observation before re-recommending
5. Recommendation outcome tracking per snapshot

Architecture:
    monitoring_snapshots (daily)
    → Day-7 checkpoint evaluation
    → 14-day outcome summarization
    → campaign_lock state transitions
    → feedback loop trigger

Usage:
    from apps.api.app.services.monitoring_14day import (
        ingest_daily_snapshot,
        evaluate_7day_checkpoint,
        check_campaign_lock,
        summarize_14day_outcome,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


# ── Campaign Lock State Machine ─────────────────────────────────────────

class CampaignLockState(StrEnum):
    """Lock states for campaign optimization windows."""

    UNLOCKED = "unlocked"           # Ready for recommendations
    LOCKED_PENDING = "locked_pending"   # Recommendation made, waiting for implementation
    LOCKED_ACTIVE = "locked_active"     # Change applied, in 14-day observation window
    LOCKED_COOLDOWN = "locked_cooldown" # 14 days passed, decisions being evaluated
    EXPIRED = "expired"                 # Observation complete, ready for next cycle


@dataclass
class CampaignLock:
    """A lock entry preventing conflicting changes within the observation window."""

    lock_id: UUID
    workspace_id: UUID
    product_id: UUID
    campaign_name: str
    state: CampaignLockState
    recommendation_type: str
    applied_change: str  # e.g., "increase_bid_20%", "add_negative_exact"
    applied_at: datetime | None = None
    lock_until: datetime | None = None  # 14 days from applied_at
    day7_checkpoint: datetime | None = None
    day14_checkpoint: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Daily Snapshot ──────────────────────────────────────────────────────

@dataclass
class DailySnapshot:
    """A single day's worth of performance data for one entity."""

    snapshot_date: date
    campaign_name: str
    ad_group_name: str
    targeting: str
    customer_search_term: str
    impressions: int = 0
    clicks: int = 0
    spend: Decimal = Decimal("0")
    sales: Decimal = Decimal("0")
    orders: int = 0
    acos: Decimal | None = None
    roas: Decimal | None = None
    cpc: Decimal | None = None
    ctr: Decimal | None = None
    cvr: Decimal | None = None
    # Tracking
    recommendation_active: bool = False
    recommendation_type: str | None = None
    days_since_recommendation: int | None = None


@dataclass(frozen=True)
class MonitoringDayResult:
    """Deterministic daily result for the PDF 14-day monitoring workflow."""

    day: int
    date_snapshot: date
    spend: Decimal
    daily_budget: Decimal
    budget_consumed_pct: Decimal
    impressions: int
    clicks: int
    orders: int
    sales: Decimal
    acos: Decimal | None
    action: str
    previous_bid: Decimal
    suggested_bid: Decimal
    locked: bool
    day7_checkpoint: bool


BID_INCREASE_MULTIPLIER = Decimal("1.10")
ACOS_LOCK_THRESHOLD = Decimal("0.50")
RATE_QUANT = Decimal("0.0001")


class Monitoring14DayService:
    """Plan-aligned 14-day monitoring cycle used by the competitor API.

    The service creates deterministic recommendation states only. It never
    mutates Amazon Ads and every actionable result remains approval-gated.
    """

    def simulate_14day_cycle(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID,
        campaign_name: str,
        daily_budget: Decimal,
        starting_bid: Decimal,
        start_date: date | None = None,
    ) -> list[MonitoringDayResult]:
        if daily_budget <= 0:
            raise ValueError("daily_budget must be greater than zero")
        if starting_bid <= 0:
            raise ValueError("starting_bid must be greater than zero")

        current_date = start_date or datetime.now(UTC).date()
        current_bid = starting_bid
        locked = False
        results: list[MonitoringDayResult] = []

        for day in range(1, 15):
            previous_bid = current_bid
            spend = self._daily_spend(day=day, bid=current_bid, starting_bid=starting_bid, daily_budget=daily_budget, locked=locked)
            sales = self._daily_sales(day=day, spend=spend)
            orders = int(sales // Decimal("25")) if sales > 0 else 0
            clicks = max(int(spend / Decimal("0.50")), 0)
            impressions = max(clicks * 50, 0)
            acos = (spend / sales).quantize(RATE_QUANT) if sales > 0 else None
            consumed_pct = ((spend / daily_budget) * Decimal("100")).quantize(RATE_QUANT)
            day7_checkpoint = day == 7
            action = "keep_running"
            suggested_bid = current_bid

            if locked:
                action = "watch_lock"
            elif day <= 7 and spend < daily_budget:
                suggested_bid = (current_bid * BID_INCREASE_MULTIPLIER).quantize(RATE_QUANT)
                action = "increase_bid"
                current_bid = suggested_bid

            if day7_checkpoint:
                total_spend = sum(item.spend for item in results) + spend
                total_sales = sum(item.sales for item in results) + sales
                cumulative_acos = (total_spend / total_sales).quantize(RATE_QUANT) if total_sales > 0 else None
                if cumulative_acos is not None and cumulative_acos < ACOS_LOCK_THRESHOLD:
                    locked = True
                    action = "watch_lock"
                    suggested_bid = previous_bid
                    current_bid = previous_bid

            results.append(MonitoringDayResult(
                day=day,
                date_snapshot=current_date + timedelta(days=day - 1),
                spend=spend,
                daily_budget=daily_budget,
                budget_consumed_pct=consumed_pct,
                impressions=impressions,
                clicks=clicks,
                orders=orders,
                sales=sales,
                acos=acos,
                action=action,
                previous_bid=previous_bid,
                suggested_bid=suggested_bid,
                locked=locked,
                day7_checkpoint=day7_checkpoint,
            ))

        return results

    @staticmethod
    def _daily_spend(*, day: int, bid: Decimal, starting_bid: Decimal, daily_budget: Decimal, locked: bool) -> Decimal:
        if locked:
            return daily_budget
        pressure = min(bid / starting_bid, Decimal("1.00"))
        if day >= 7:
            pressure = Decimal("1.00")
        return min(daily_budget, daily_budget * pressure * Decimal("0.75")).quantize(RATE_QUANT)

    @staticmethod
    def _daily_sales(*, day: int, spend: Decimal) -> Decimal:
        if day < 7:
            return (spend * Decimal("2.20")).quantize(RATE_QUANT)
        return (spend * Decimal("2.50")).quantize(RATE_QUANT)


# ── Day-7 Checkpoint ────────────────────────────────────────────────────

@dataclass
class Day7Checkpoint:
    """Results of the 7-day ACOS checkpoint evaluation.

    This is the early-warning gate: if a bid increase hasn't shown
    positive ACOS movement by day 7, it triggers a review before
    the full 14-day window closes.
    """

    recommendation_id: UUID
    campaign_name: str
    recommendation_type: str
    applied_at: datetime
    checkpoint_date: date

    # Pre-change metrics (7 days before change)
    pre_week_spend: Decimal
    pre_week_sales: Decimal
    pre_week_acos: Decimal | None
    pre_week_orders: int
    pre_week_clicks: int

    # Post-change metrics (7 days after change)
    post_week_spend: Decimal
    post_week_sales: Decimal
    post_week_acos: Decimal | None
    post_week_orders: int
    post_week_clicks: int

    # Evaluation
    acos_delta_pct: float = 0.0
    status: str = "on_track"  # on_track | needs_review | flag_early
    recommendation: str = ""
    early_termination_recommended: bool = False


# ── 14-Day Outcome ──────────────────────────────────────────────────────

@dataclass
class Day14Outcome:
    """Full 14-day observation outcome for a recommendation."""

    recommendation_id: UUID
    campaign_name: str
    recommendation_type: str
    applied_at: datetime
    observation_end: date

    # Pre-change metrics
    pre_spend: Decimal
    pre_sales: Decimal
    pre_acos: Decimal | None
    pre_orders: int

    # Post-change metrics
    post_spend: Decimal
    post_sales: Decimal
    post_acos: Decimal | None
    post_orders: int

    # Deltas
    spend_delta_pct: float = 0.0
    sales_delta_pct: float = 0.0
    acos_delta_pct: float = 0.0
    orders_delta_pct: float = 0.0

    # Outcome classification
    outcome: str = "unchanged"  # improved | worsened | unchanged | insufficient_data
    confidence: str = "medium"  # high | medium | low
    feedback_triggered: bool = False

    # Rule calibration suggestions
    rule_adjustments: list[dict[str, Any]] = field(default_factory=list)


# ── Core Functions ──────────────────────────────────────────────────────


def ingest_daily_snapshot(
    *,
    workspace_id: UUID,
    product_id: UUID,
    snapshot: DailySnapshot,
    campaign_locks: dict[str, CampaignLock] | None = None,
) -> dict[str, Any]:
    """Ingest a single day's snapshot into the monitoring time-series.

    Args:
        workspace_id: Workspace scope
        product_id: Product scope
        snapshot: Daily performance data for one entity
        campaign_locks: Active campaign locks to check against

    Returns:
        Dict with ingestion status and any triggered conditions
    """
    locks = campaign_locks or {}
    campaign_key = snapshot.campaign_name.lower().strip()

    # Check if this campaign has an active lock
    active_lock = locks.get(campaign_key)
    triggered: list[str] = []

    if active_lock and active_lock.state == CampaignLockState.LOCKED_ACTIVE:
        # Check if we've hit Day 7
        if active_lock.applied_at:
            days_since = (snapshot.snapshot_date - active_lock.applied_at.date()).days

            if days_since > 0:
                snapshot.days_since_recommendation = days_since
                snapshot.recommendation_active = True
                snapshot.recommendation_type = active_lock.recommendation_type

            if days_since >= 7 and not active_lock.day7_checkpoint:
                triggered.append("day7_checkpoint")

            if days_since >= 14:
                triggered.append("day14_outcome")

    return {
        "snapshot_ingested": True,
        "campaign_locked": campaign_key in locks,
        "lock_state": str(active_lock.state) if active_lock else None,
        "days_since_recommendation": snapshot.days_since_recommendation,
        "triggered_conditions": triggered,
    }


def evaluate_7day_checkpoint(
    *,
    recommendation_id: UUID,
    campaign_name: str,
    recommendation_type: str,
    applied_at: datetime,
    pre_week_snapshots: list[DailySnapshot],
    post_week_snapshots: list[DailySnapshot],
) -> Day7Checkpoint:
    """Evaluate the Day-7 ACOS checkpoint for early warning.

    If a bid increase hasn't produced positive ACOS movement by day 7,
    this is flagged for review before the full 14-day window closes.
    """
    # Aggregate pre-week metrics
    pre_spend = sum(s.spend for s in pre_week_snapshots)
    pre_sales = sum(s.sales for s in pre_week_snapshots)
    pre_orders = sum(s.orders for s in pre_week_snapshots)
    pre_clicks = sum(s.clicks for s in pre_week_snapshots)
    pre_acos = (pre_spend / pre_sales) if pre_sales > 0 else None

    # Aggregate post-week metrics
    post_spend = sum(s.spend for s in post_week_snapshots)
    post_sales = sum(s.sales for s in post_week_snapshots)
    post_orders = sum(s.orders for s in post_week_snapshots)
    post_clicks = sum(s.clicks for s in post_week_snapshots)
    post_acos = (post_spend / post_sales) if post_sales > 0 else None

    # Calculate ACOS delta
    acos_delta_pct = 0.0
    if pre_acos and post_acos:
        acos_delta_pct = float((post_acos - pre_acos) / pre_acos * 100) if pre_acos > 0 else 0.0

    checkpoint_date = applied_at.date() + timedelta(days=7)
    status = "on_track"
    recommendation = ""
    early_termination = False

    if recommendation_type == "increase_bid":
        # Bid increase: ACOS should NOT have worsened significantly
        if acos_delta_pct > 20.0:
            status = "flag_early"
            recommendation = "ACOS increased significantly after bid increase. Consider early review."
            early_termination = acos_delta_pct > 50.0
        elif acos_delta_pct > 10.0:
            status = "needs_review"
            recommendation = "ACOS trending up after bid increase. Monitor closely."
        elif post_sales < pre_sales * Decimal("0.8"):
            status = "needs_review"
            recommendation = "Sales declined despite bid increase. Review targeting."

    elif recommendation_type in {"add_negative_exact", "add_negative_phrase"}:
        # Negative keyword: spend should be zero or near-zero
        if post_spend > Decimal("1.00"):
            status = "needs_review"
            recommendation = "Spend still occurring on negative keyword — verify implementation."
        else:
            status = "on_track"
            recommendation = "Negative keyword effective — spend eliminated."

    elif recommendation_type == "decrease_bid":
        # Bid decrease: ACOS should improve without killing sales
        if acos_delta_pct < -5.0 and post_sales >= pre_sales * Decimal("0.5"):
            status = "on_track"
            recommendation = "Bid decrease improving ACOS with acceptable sales retention."
        elif post_sales < pre_sales * Decimal("0.3"):
            status = "flag_early"
            recommendation = "Sales dropped severely after bid decrease. Consider reverting."
            early_termination = True

    return Day7Checkpoint(
        recommendation_id=recommendation_id,
        campaign_name=campaign_name,
        recommendation_type=recommendation_type,
        applied_at=applied_at,
        checkpoint_date=checkpoint_date,
        pre_week_spend=pre_spend,
        pre_week_sales=pre_sales,
        pre_week_acos=pre_acos,
        pre_week_orders=pre_orders,
        pre_week_clicks=pre_clicks,
        post_week_spend=post_spend,
        post_week_sales=post_sales,
        post_week_acos=post_acos,
        post_week_orders=post_orders,
        post_week_clicks=post_clicks,
        acos_delta_pct=round(acos_delta_pct, 1),
        status=status,
        recommendation=recommendation,
        early_termination_recommended=early_termination,
    )


def check_campaign_lock(
    *,
    campaign_name: str,
    active_locks: list[CampaignLock],
) -> CampaignLock | None:
    """Check if a campaign has an active lock preventing new recommendations.

    A campaign is locked if:
    - A recommendation was made within the last 14 days
    - The lock hasn't expired
    - No conflicting recommendation type is active
    """
    campaign_key = campaign_name.lower().strip()
    now = datetime.now(UTC)

    for lock in active_locks:
        if lock.campaign_name.lower().strip() != campaign_key:
            continue

        if lock.state == CampaignLockState.EXPIRED:
            continue

        if lock.lock_until and now > lock.lock_until:
            # Lock has expired — should transition to EXPIRED
            continue

        return lock

    return None


def summarize_14day_outcome(
    *,
    recommendation_id: UUID,
    campaign_name: str,
    recommendation_type: str,
    applied_at: datetime,
    pre_period_snapshots: list[DailySnapshot],
    post_period_snapshots: list[DailySnapshot],
    minimum_clicks_for_confidence: int = 10,
) -> Day14Outcome:
    """Summarize the full 14-day outcome of a recommendation.

    This is the primary closed-loop evaluation that determines:
    1. Whether the recommendation improved, worsened, or had no effect
    2. Confidence level based on data volume
    3. Rule calibration suggestions for the learning feedback loop
    """
    if not pre_period_snapshots or not post_period_snapshots:
        return Day14Outcome(
            recommendation_id=recommendation_id,
            campaign_name=campaign_name,
            recommendation_type=recommendation_type,
            applied_at=applied_at,
            observation_end=applied_at.date() + timedelta(days=14),
            pre_spend=Decimal("0"),
            pre_sales=Decimal("0"),
            pre_acos=None,
            pre_orders=0,
            post_spend=Decimal("0"),
            post_sales=Decimal("0"),
            post_acos=None,
            post_orders=0,
            outcome="insufficient_data",
            confidence="low",
        )

    # Aggregate pre-period
    pre_spend = sum(s.spend for s in pre_period_snapshots)
    pre_sales = sum(s.sales for s in pre_period_snapshots)
    pre_orders = sum(s.orders for s in pre_period_snapshots)
    pre_clicks = sum(s.clicks for s in pre_period_snapshots)
    pre_acos = (pre_spend / pre_sales) if pre_sales > 0 else None

    # Aggregate post-period
    post_spend = sum(s.spend for s in post_period_snapshots)
    post_sales = sum(s.sales for s in post_period_snapshots)
    post_orders = sum(s.orders for s in post_period_snapshots)
    post_clicks = sum(s.clicks for s in post_period_snapshots)
    post_acos = (post_spend / post_sales) if post_sales > 0 else None

    # Calculate deltas
    spend_delta = float((post_spend - pre_spend) / pre_spend * 100) if pre_spend > 0 else 0.0
    sales_delta = float((post_sales - pre_sales) / pre_sales * 100) if pre_sales > 0 else 0.0
    acos_delta = 0.0
    if pre_acos and post_acos and pre_acos > 0:
        acos_delta = float((post_acos - pre_acos) / pre_acos * 100)
    orders_delta = float((post_orders - pre_orders) / pre_orders * 100) if pre_orders > 0 else 0.0

    # Classify outcome
    outcome = _classify_14day_outcome(
        recommendation_type=recommendation_type,
        pre_spend=float(pre_spend),
        pre_sales=float(pre_sales),
        pre_acos=float(pre_acos) if pre_acos else 0.0,
        post_spend=float(post_spend),
        post_sales=float(post_sales),
        post_acos=float(post_acos) if post_acos else 0.0,
        acos_delta=acos_delta,
        sales_delta=sales_delta,
    )

    # Determine confidence
    total_clicks = post_clicks
    confidence = "low"
    if total_clicks >= minimum_clicks_for_confidence * 5:
        confidence = "high"
    elif total_clicks >= minimum_clicks_for_confidence * 2:
        confidence = "medium"

    # Generate rule calibration suggestions
    adjustments = _generate_rule_adjustments(
        recommendation_type=recommendation_type,
        outcome=outcome,
        acos_delta=acos_delta,
        sales_delta=sales_delta,
    )

    return Day14Outcome(
        recommendation_id=recommendation_id,
        campaign_name=campaign_name,
        recommendation_type=recommendation_type,
        applied_at=applied_at,
        observation_end=applied_at.date() + timedelta(days=14),
        pre_spend=pre_spend,
        pre_sales=pre_sales,
        pre_acos=pre_acos,
        pre_orders=pre_orders,
        post_spend=post_spend,
        post_sales=post_sales,
        post_acos=post_acos,
        post_orders=post_orders,
        spend_delta_pct=round(spend_delta, 1),
        sales_delta_pct=round(sales_delta, 1),
        acos_delta_pct=round(acos_delta, 1),
        orders_delta_pct=round(orders_delta, 1),
        outcome=outcome,
        confidence=confidence,
        feedback_triggered=True,
        rule_adjustments=adjustments,
    )


def _classify_14day_outcome(
    *,
    recommendation_type: str,
    pre_spend: float,
    pre_sales: float,
    pre_acos: float,
    post_spend: float,
    post_sales: float,
    post_acos: float,
    acos_delta: float,
    sales_delta: float,
) -> str:
    """Classify the 14-day outcome based on recommendation type and metric deltas."""
    if pre_spend == 0 and post_spend == 0:
        return "insufficient_data"

    if recommendation_type == "increase_bid":
        # Positive: sales up, ACOS didn't explode
        if sales_delta > 10.0 and acos_delta < 15.0:
            return "improved"
        if acos_delta > 30.0:
            return "worsened"
        if sales_delta < -20.0:
            return "worsened"

    elif recommendation_type == "decrease_bid":
        # Positive: ACOS improved without sales dying
        if acos_delta < -5.0 and sales_delta > -30.0:
            return "improved"
        if sales_delta < -50.0:
            return "worsened"

    elif recommendation_type in {"add_negative_exact", "add_negative_phrase"}:
        # Positive: spend eliminated
        if post_spend < 1.0:
            return "improved"
        if post_spend > pre_spend * 0.5:
            return "worsened"

    elif recommendation_type in {"pause_review", "pause_keyword"}:
        if post_spend < pre_spend * 0.1:
            return "improved"
        if post_spend > pre_spend * 0.3:
            return "worsened"

    elif recommendation_type in {"harvest_to_exact", "move_to_exact"}:
        if acos_delta < -5.0 and sales_delta >= -10.0:
            return "improved"
        if acos_delta > 15.0:
            return "worsened"

    # Default: general health check
    if post_acos < pre_acos * 0.95 and sales_delta >= -20.0:
        return "improved"
    if post_acos > pre_acos * 1.15:
        return "worsened"

    return "unchanged"


def _generate_rule_adjustments(
    *,
    recommendation_type: str,
    outcome: str,
    acos_delta: float,
    sales_delta: float,
) -> list[dict[str, Any]]:
    """Generate rule calibration suggestions from 14-day outcomes."""
    adjustments = []

    if outcome == "improved":
        # Rule is working — maybe tighten?
        adjustments.append({
            "rule_name": _rule_name_for_type(recommendation_type),
            "suggestion": "tighten",
            "confidence_increase": 0.05,
            "reason": "Rule recommendation improved outcomes.",
        })
    elif outcome == "worsened":
        adjustments.append({
            "rule_name": _rule_name_for_type(recommendation_type),
            "suggestion": "loosen",
            "confidence_decrease": 0.10,
            "reason": "Rule recommendation worsened outcomes. Review thresholds.",
        })
    elif outcome == "unchanged":
        adjustments.append({
            "rule_name": _rule_name_for_type(recommendation_type),
            "suggestion": "review",
            "reason": "No significant impact detected. Rule may need stricter filters.",
        })

    return adjustments


def _rule_name_for_type(recommendation_type: str) -> str:
    """Map recommendation type to rule name for calibration."""
    mapping = {
        "increase_bid": "bid_optimization_rule",
        "decrease_bid": "bid_optimization_rule",
        "set_bid": "bid_optimization_rule",
        "add_negative_exact": "negative_keyword_rule",
        "add_negative_phrase": "negative_keyword_rule",
        "pause_review": "pause_review_rule",
        "pause_keyword": "pause_review_rule",
        "pause_target": "pause_review_rule",
        "harvest_to_exact": "harvest_rule",
        "move_to_exact": "harvest_rule",
        "keep_running": "harvest_rule",
        "budget_review": "budget_reallocation_rule",
        "increase_campaign_budget": "budget_reallocation_rule",
    }
    return mapping.get(recommendation_type, "evidence_rule")


# ── Lock Lifecycle Management ───────────────────────────────────────────


def create_campaign_lock(
    *,
    workspace_id: UUID,
    product_id: UUID,
    campaign_name: str,
    recommendation_type: str,
    applied_change: str,
) -> CampaignLock:
    """Create a campaign lock after a recommendation is approved/applied.

    The lock prevents new recommendations on the same campaign
    for 14 days while the change is being evaluated.
    """
    now = datetime.now(UTC)
    return CampaignLock(
        lock_id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        campaign_name=campaign_name,
        state=CampaignLockState.LOCKED_PENDING,
        recommendation_type=recommendation_type,
        applied_change=applied_change,
        applied_at=None,
        lock_until=now + timedelta(days=14),
        day7_checkpoint=None,
        day14_checkpoint=None,
        created_at=now,
    )


def advance_lock_state(
    lock: CampaignLock,
    *,
    event: str,  # "applied", "day7_passed", "day14_passed", "expire"
    outcome: Day14Outcome | None = None,
) -> CampaignLock:
    """Advance a campaign lock through its lifecycle states."""
    transitions = {
        ("LOCKED_PENDING", "applied"): CampaignLockState.LOCKED_ACTIVE,
        ("LOCKED_ACTIVE", "day7_passed"): CampaignLockState.LOCKED_ACTIVE,  # Still active, just marking checkpoint
        ("LOCKED_ACTIVE", "day14_passed"): CampaignLockState.LOCKED_COOLDOWN,
        ("LOCKED_COOLDOWN", "expire"): CampaignLockState.EXPIRED,
    }

    # Map the StrEnum value (lowercase with underscores) to transition key format
    value_to_key = {
        "unlocked": "UNLOCKED",
        "locked_pending": "LOCKED_PENDING",
        "locked_active": "LOCKED_ACTIVE",
        "locked_cooldown": "LOCKED_COOLDOWN",
        "expired": "EXPIRED",
    }
    current = value_to_key.get(lock.state.value, "LOCKED_PENDING")
    new_state = transitions.get((current, event))

    if new_state is None:
        # Check for direct expiration
        if event == "expire":
            new_state = CampaignLockState.EXPIRED

    if new_state is None:
        return lock  # No valid transition

    return CampaignLock(
        lock_id=lock.lock_id,
        workspace_id=lock.workspace_id,
        product_id=lock.product_id,
        campaign_name=lock.campaign_name,
        state=new_state,
        recommendation_type=lock.recommendation_type,
        applied_change=lock.applied_change,
        applied_at=datetime.now(UTC) if event == "applied" else lock.applied_at,
        lock_until=lock.lock_until,
        day7_checkpoint=datetime.now(UTC) if event == "day7_passed" else lock.day7_checkpoint,
        day14_checkpoint=datetime.now(UTC) if event == "day14_passed" else lock.day14_checkpoint,
        created_at=lock.created_at,
    )
