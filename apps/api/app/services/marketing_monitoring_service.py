from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MonitoringActionType(StrEnum):
    INCREASE_BID = "increase_bid"
    LOCK_CAMPAIGN = "lock_campaign"
    NO_ACTION = "no_action"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CampaignDayRecord:
    campaign_id: str
    day_number: int
    daily_spend: Decimal
    daily_budget: Decimal
    current_bid: Decimal
    total_spend_to_date: Decimal
    total_sales_to_date: Decimal
    is_locked: bool = False


@dataclass
class MonitoringAction:
    campaign_id: str
    day_number: int
    action_type: MonitoringActionType
    new_bid: Optional[Decimal]
    reason: str
    acos: Optional[Decimal] = None


@dataclass
class MonitoringReport:
    campaign_id: str
    actions: list[MonitoringAction] = field(default_factory=list)
    final_bid: Decimal = field(default_factory=lambda: Decimal("0"))
    is_locked: bool = False
    day7_acos: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MarketingMonitoringService:
    """Pure service implementing Phase 3 of the marketing pipeline: 14-day monitoring.

    Design constraints:
      - Pure service: no DB, no HTTP, no side effects.
      - All bid arithmetic uses Decimal for precision.
      - Lock state from day 7 propagates forward; no further bid changes for days 8-14.
    """

    _BID_INCREASE_FACTOR = Decimal("1.10")
    _ACOS_LOCK_THRESHOLD = Decimal("0.50")

    def evaluate_day(self, record: CampaignDayRecord) -> MonitoringAction:
        if record.is_locked:
            return MonitoringAction(
                campaign_id=record.campaign_id,
                day_number=record.day_number,
                action_type=MonitoringActionType.NO_ACTION,
                new_bid=None,
                reason="Campaign locked after day-7 ACOS check.",
            )

        if record.day_number <= 7:
            if record.daily_spend < record.daily_budget:
                new_bid = record.current_bid * self._BID_INCREASE_FACTOR
                return MonitoringAction(
                    campaign_id=record.campaign_id,
                    day_number=record.day_number,
                    action_type=MonitoringActionType.INCREASE_BID,
                    new_bid=new_bid,
                    reason=(
                        f"Daily spend {record.daily_spend} < budget {record.daily_budget}; "
                        f"bid increased by 10%."
                    ),
                )

            if record.day_number == 7 and record.total_sales_to_date > Decimal("0"):
                acos = record.total_spend_to_date / record.total_sales_to_date
                if acos < self._ACOS_LOCK_THRESHOLD:
                    return MonitoringAction(
                        campaign_id=record.campaign_id,
                        day_number=record.day_number,
                        action_type=MonitoringActionType.LOCK_CAMPAIGN,
                        new_bid=None,
                        reason=(
                            f"Day-7 ACOS {acos:.4f} < {self._ACOS_LOCK_THRESHOLD}; "
                            f"campaign locked for days 8-14."
                        ),
                        acos=acos,
                    )

            return MonitoringAction(
                campaign_id=record.campaign_id,
                day_number=record.day_number,
                action_type=MonitoringActionType.NO_ACTION,
                new_bid=None,
                reason="Budget fully consumed.",
            )

        return MonitoringAction(
            campaign_id=record.campaign_id,
            day_number=record.day_number,
            action_type=MonitoringActionType.NO_ACTION,
            new_bid=None,
            reason="Monitoring period, no optimization.",
        )

    def _evaluate_day_7_acos(
        self,
        record: CampaignDayRecord,
        current_bid: Decimal,
    ) -> Optional[MonitoringAction]:
        if record.total_sales_to_date <= Decimal("0"):
            return None
        acos = record.total_spend_to_date / record.total_sales_to_date
        if acos < self._ACOS_LOCK_THRESHOLD:
            return MonitoringAction(
                campaign_id=record.campaign_id,
                day_number=record.day_number,
                action_type=MonitoringActionType.LOCK_CAMPAIGN,
                new_bid=None,
                reason=(
                    f"Day-7 ACOS {acos:.4f} < {self._ACOS_LOCK_THRESHOLD}; "
                    f"campaign locked for days 8-14."
                ),
                acos=acos,
            )
        return None

    def run_14_day_simulation(
        self, records: list[CampaignDayRecord]
    ) -> list[MonitoringReport]:
        """Simulate 14 days of monitoring for all campaigns.

        Groups records by campaign_id, processes days in order, tracks bid and lock state.
        """
        grouped: dict[str, list[CampaignDayRecord]] = {}
        for record in records:
            grouped.setdefault(record.campaign_id, []).append(record)

        reports: list[MonitoringReport] = []

        for campaign_id, day_records in grouped.items():
            day_records_sorted = sorted(day_records, key=lambda r: r.day_number)

            current_bid: Decimal = day_records_sorted[0].current_bid if day_records_sorted else Decimal("1.00")
            is_locked: bool = False
            day7_acos: Optional[Decimal] = None
            actions: list[MonitoringAction] = []

            for raw_record in day_records_sorted:
                record = CampaignDayRecord(
                    campaign_id=raw_record.campaign_id,
                    day_number=raw_record.day_number,
                    daily_spend=raw_record.daily_spend,
                    daily_budget=raw_record.daily_budget,
                    current_bid=current_bid,
                    total_spend_to_date=raw_record.total_spend_to_date,
                    total_sales_to_date=raw_record.total_sales_to_date,
                    is_locked=is_locked,
                )

                if record.day_number == 7 and not is_locked:
                    # Step 1: budget consumption check
                    if record.daily_spend < record.daily_budget:
                        new_bid = current_bid * self._BID_INCREASE_FACTOR
                        actions.append(MonitoringAction(
                            campaign_id=campaign_id,
                            day_number=record.day_number,
                            action_type=MonitoringActionType.INCREASE_BID,
                            new_bid=new_bid,
                            reason=(
                                f"Daily spend {record.daily_spend} < budget {record.daily_budget}; "
                                f"bid increased by 10%."
                            ),
                        ))
                        current_bid = new_bid
                        record = CampaignDayRecord(
                            campaign_id=record.campaign_id,
                            day_number=record.day_number,
                            daily_spend=record.daily_spend,
                            daily_budget=record.daily_budget,
                            current_bid=current_bid,
                            total_spend_to_date=record.total_spend_to_date,
                            total_sales_to_date=record.total_sales_to_date,
                            is_locked=is_locked,
                        )

                    # Step 2: ACOS profitability check
                    lock_action = self._evaluate_day_7_acos(record, current_bid)
                    if lock_action is not None:
                        actions.append(lock_action)
                        is_locked = True
                        day7_acos = lock_action.acos
                    else:
                        if record.daily_spend >= record.daily_budget:
                            actions.append(MonitoringAction(
                                campaign_id=campaign_id,
                                day_number=record.day_number,
                                action_type=MonitoringActionType.NO_ACTION,
                                new_bid=None,
                                reason="Budget fully consumed.",
                            ))
                else:
                    action = self.evaluate_day(record)
                    actions.append(action)

                    if action.action_type == MonitoringActionType.INCREASE_BID and action.new_bid is not None:
                        current_bid = action.new_bid
                    elif action.action_type == MonitoringActionType.LOCK_CAMPAIGN:
                        is_locked = True
                        day7_acos = action.acos

            reports.append(MonitoringReport(
                campaign_id=campaign_id,
                actions=actions,
                final_bid=current_bid,
                is_locked=is_locked,
                day7_acos=day7_acos,
            ))

        return reports
