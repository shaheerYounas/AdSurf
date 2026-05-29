"""14-day automated monitoring system (items 16-20).

Implements the plan's monitoring cycle:
- Days 1-7: Budget consumption check with 10% bid increases
- Day 7: ACOS evaluation (lock if < 50%)
- Days 8-14: Locked campaigns receive no changes
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError

DAILY_BUDGET_DEFAULT = Decimal("10.0000")
BID_INCREASE_MULTIPLIER = Decimal("1.10")
DEFAULT_BID = Decimal("1.0000")
ACOS_LOCK_THRESHOLD = Decimal("50.0000")
DAYS_7 = 7
DAYS_14 = 14
LOCK_DURATION_DAYS = 7
MAX_CONSECUTIVE_INCREASES = 5
BUDGET_CONSUMPTION_THRESHOLD = Decimal("0.80")  # 80% of daily budget


@dataclass(frozen=True)
class Monitoring14DayResult:
    campaign_name: str
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


class Monitoring14DayService:
    """14-day automated monitoring system.

    In production, this would be driven by a scheduled Lambda/cron job that:
    1. Pulls daily performance reports for each campaign
    2. Inserts daily_budget_snapshots rows
    3. On Day 7, evaluates ACOS and creates campaign_locks if needed
    4. On Days 1-7, increases bids by 10% if budget not consumed
    5. On Days 8-14, skips locked campaigns

    For the MVP, this is a synchronous endpoint that simulates/summarizes
    what the monitoring cycle would produce.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_database_engine()

    def simulate_14day_cycle(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID,
        campaign_name: str,
        daily_budget: Decimal = DAILY_BUDGET_DEFAULT,
        starting_bid: Decimal = DEFAULT_BID,
    ) -> list[Monitoring14DayResult]:
        results: list[Monitoring14DayResult] = []
        current_bid = starting_bid
        consecutive_increases = 0
        is_locked = False
        lock_until: date | None = None

        for day in range(1, DAYS_14 + 1):
            snapshot_date = date.today() - timedelta(days=DAYS_14 - day)
            spend = _simulate_daily_spend(daily_budget, day, is_locked)
            impressions = int(spend * Decimal("100"))
            clicks = int(spend * Decimal("2"))
            orders = int(spend * Decimal("0.05"))
            sales = Decimal(orders) * Decimal("25.0000") if orders > 0 else Decimal("0")
            acos = (spend / sales * Decimal("100")).quantize(Decimal("0.01")) if sales > 0 else None

            budget_consumed_pct = (spend / daily_budget * Decimal("100")).quantize(Decimal("0.1"))
            action = "keep_running"
            day7_checkpoint = False

            if is_locked and lock_until and snapshot_date <= lock_until:
                action = "locked_no_changes"
            elif day <= DAYS_7 and budget_consumed_pct < BUDGET_CONSUMPTION_THRESHOLD * 100:
                if consecutive_increases < MAX_CONSECUTIVE_INCREASES:
                    current_bid = (current_bid * BID_INCREASE_MULTIPLIER).quantize(Decimal("0.01"))
                    consecutive_increases += 1
                    action = f"bid_increased_10pct_to_{current_bid}"
                else:
                    action = "max_increases_reached"
            elif day == DAYS_7:
                day7_checkpoint = True
                if acos is not None and acos < ACOS_LOCK_THRESHOLD:
                    is_locked = True
                    lock_until = snapshot_date + timedelta(days=LOCK_DURATION_DAYS)
                    action = "locked_acos_below_50pct"
                    self._record_lock(
                        workspace_id=workspace_id,
                        campaign_name=campaign_name,
                        acos=acos,
                        lock_until=lock_until,
                    )
                else:
                    action = "continue_monitoring_acos_above_50pct"

            self._record_daily_snapshot(
                workspace_id=workspace_id,
                product_id=product_id,
                campaign_name=campaign_name,
                snapshot_date=snapshot_date,
                daily_budget=daily_budget,
                spend=spend,
                impressions=impressions,
                clicks=clicks,
                orders=orders,
                sales=sales,
                acos=acos,
                bid_multiplier=BID_INCREASE_MULTIPLIER if action.startswith("bid_increased") else Decimal("1.0"),
                previous_bid=current_bid / BID_INCREASE_MULTIPLIER if action.startswith("bid_increased") else current_bid,
                suggested_bid=current_bid,
            )

            if day7_checkpoint:
                self._record_day7_checkpoint(
                    workspace_id=workspace_id,
                    product_id=product_id,
                    campaign_name=campaign_name,
                    acos=acos or Decimal("0"),
                    decision="locked" if is_locked else "continue_monitoring",
                    lock_until=lock_until,
                )

            results.append(Monitoring14DayResult(
                campaign_name=campaign_name,
                day=day,
                date_snapshot=snapshot_date,
                spend=spend,
                daily_budget=daily_budget,
                budget_consumed_pct=budget_consumed_pct,
                impressions=impressions,
                clicks=clicks,
                orders=orders,
                sales=sales,
                acos=acos,
                action=action,
                previous_bid=current_bid / BID_INCREASE_MULTIPLIER if action.startswith("bid_increased") else current_bid,
                suggested_bid=current_bid,
                locked=is_locked,
                day7_checkpoint=day7_checkpoint,
            ))

        return results

    def _record_daily_snapshot(self, *, workspace_id: UUID, product_id: UUID, campaign_name: str, snapshot_date: date, daily_budget: Decimal, spend: Decimal, impressions: int, clicks: int, orders: int, sales: Decimal, acos: Decimal | None, bid_multiplier: Decimal, previous_bid: Decimal, suggested_bid: Decimal) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into daily_budget_snapshots (
                        id, workspace_id, product_id, campaign_name, snapshot_date,
                        daily_budget, spend, impressions, clicks, orders, sales, acos,
                        bid_multiplier, previous_bid, suggested_bid
                    ) values (
                        gen_random_uuid(), :workspace_id, :product_id, :campaign_name, :snapshot_date,
                        :daily_budget, :spend, :impressions, :clicks, :orders, :sales, :acos,
                        :bid_multiplier, :previous_bid, :suggested_bid
                    )
                    on conflict (workspace_id, product_id, campaign_name, snapshot_date)
                    do update set spend = :spend, impressions = :impressions, clicks = :clicks,
                        orders = :orders, sales = :sales, acos = :acos,
                        bid_multiplier = :bid_multiplier, previous_bid = :previous_bid,
                        suggested_bid = :suggested_bid
                    """
                ),
                {
                    "workspace_id": workspace_id, "product_id": product_id,
                    "campaign_name": campaign_name, "snapshot_date": snapshot_date,
                    "daily_budget": str(daily_budget), "spend": str(spend),
                    "impressions": impressions, "clicks": clicks,
                    "orders": orders, "sales": str(sales),
                    "acos": str(acos) if acos is not None else None,
                    "bid_multiplier": str(bid_multiplier),
                    "previous_bid": str(previous_bid), "suggested_bid": str(suggested_bid),
                },
            )

    def _record_lock(self, *, workspace_id: UUID, campaign_name: str, acos: Decimal, lock_until: date) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into campaign_locks (
                        id, workspace_id, campaign_name, status, acos_at_lock, locked_until
                    ) values (
                        gen_random_uuid(), :workspace_id, :campaign_name, 'locked',
                        :acos, :locked_until
                    )
                    on conflict (workspace_id, campaign_name)
                    do update set status = 'locked', acos_at_lock = :acos,
                        locked_until = :locked_until, locked_at = now(),
                        unlocked_at = null
                    """
                ),
                {
                    "workspace_id": workspace_id, "campaign_name": campaign_name,
                    "acos": str(acos), "locked_until": lock_until,
                },
            )

    def _record_day7_checkpoint(self, *, workspace_id: UUID, product_id: UUID, campaign_name: str, acos: Decimal, decision: str, lock_until: date | None) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into day7_checkpoints (
                        id, workspace_id, product_id, campaign_name,
                        total_spend_7d, total_sales_7d, acos_7d,
                        decision, locked_until
                    ) values (
                        gen_random_uuid(), :workspace_id, :product_id, :campaign_name,
                        :spend, :sales, :acos, :decision, :locked_until
                    )
                    on conflict (workspace_id, product_id, campaign_name)
                    do update set acos_7d = :acos, decision = :decision,
                        locked_until = :locked_until, evaluated_at = now()
                    """
                ),
                {
                    "workspace_id": workspace_id, "product_id": product_id,
                    "campaign_name": campaign_name,
                    "spend": str(Decimal("70")),  # Simulated 7-day spend
                    "sales": str(Decimal("70") / acos * Decimal("100") if acos > 0 else Decimal("0")),
                    "acos": str(acos), "decision": decision,
                    "locked_until": lock_until,
                },
            )


def _simulate_daily_spend(daily_budget: Decimal, day: int, is_locked: bool) -> Decimal:
    """Simulate daily spend. Early days spend less, ramps up over time."""
    if is_locked:
        return daily_budget * Decimal("0.85")  # Stable spend during lock
    ramp = min(Decimal(day) / Decimal("7"), Decimal("1"))
    noise = Decimal("0.85") + Decimal("0.30") * (1 - ramp)  # More variance early on
    return (daily_budget * ramp * noise).quantize(Decimal("0.01"))