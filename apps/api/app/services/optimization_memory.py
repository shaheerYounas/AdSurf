"""Pattern-level optimization memory.

Per-row history of every recommendation is too noisy and too large to feed
back into the AI brain on every run. Instead we aggregate prior outcomes into
*pattern buckets* keyed by (archetype, action, strategy_mode), where archetype
is a coarse, learnable description of the targeted entity:

    archetype = (
        match_type,             # exact / phrase / broad / auto
        acos_band,              # under_target / near_target / 1-2x_target / 2x+_target / no_orders
        click_volume_band,      # micro / low / mid / high
    )

For each bucket we summarize how the action played out — median ACOS delta,
spend change, sample size, success rate — over the available history.

The brain prompt receives only the buckets that match candidates in the
current run, not the raw history. Per-row history remains in the audit trail
(`Recommendation.evidence_json`) but is not loaded into the prompt.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any, Iterable

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    Recommendation,
    RecommendationStatus,
    RecommendationType,
)


@dataclass(frozen=True)
class PatternKey:
    match_type: str
    acos_band: str
    click_volume_band: str
    action: str
    strategy_mode: str

    def to_dict(self) -> dict[str, str]:
        return {
            "match_type": self.match_type,
            "acos_band": self.acos_band,
            "click_volume_band": self.click_volume_band,
            "action": self.action,
            "strategy_mode": self.strategy_mode,
        }


@dataclass(frozen=True)
class PatternOutcome:
    """Aggregated outcome of a pattern across its history."""

    key: PatternKey
    sample_size: int
    median_acos_delta_pct: float | None
    median_spend_delta_pct: float | None
    success_rate: float
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.key.to_dict(),
            "sample_size": self.sample_size,
            "median_acos_delta_pct": self.median_acos_delta_pct,
            "median_spend_delta_pct": self.median_spend_delta_pct,
            "success_rate": self.success_rate,
            "summary": self.summary,
        }


def archetype_for_snapshot(
    snapshot: MonitoringSnapshot,
    *,
    target_acos: Decimal,
) -> dict[str, str]:
    """Compute the archetype dimensions for a single snapshot."""

    return {
        "match_type": _normalize_match_type(snapshot.match_type),
        "acos_band": _acos_band(snapshot, target_acos=target_acos),
        "click_volume_band": _click_band(snapshot.clicks),
    }


def build_pattern_index(
    *,
    prior_recommendations: Iterable[Recommendation],
    prior_snapshots: Iterable[MonitoringSnapshot],
    follow_up_snapshots: Iterable[MonitoringSnapshot],
    strategy_mode: str,
    target_acos: Decimal,
) -> dict[str, PatternOutcome]:
    """Aggregate prior recommendations + their measured outcomes into patterns.

    `prior_snapshots` must be the snapshots the recommendations were generated
    against; `follow_up_snapshots` must be the next-period snapshots where we
    can observe the outcome. Snapshots are matched by entity key.

    Returns a dict mapping a stable string key (use `pattern_key_to_str`) to
    a PatternOutcome for every bucket with at least one observation.
    """

    snap_by_id = {s.id: s for s in prior_snapshots}
    follow_by_key = {_entity_key(s): s for s in follow_up_snapshots}

    buckets: dict[PatternKey, list[dict[str, float]]] = defaultdict(list)

    for rec in prior_recommendations:
        if rec.status != RecommendationStatus.APPROVED:
            continue

        before = snap_by_id.get(rec.snapshot_id) if rec.snapshot_id else None
        if before is None:
            continue
        after = follow_by_key.get(_entity_key(before))
        if after is None:
            continue

        archetype = archetype_for_snapshot(before, target_acos=target_acos)
        key = PatternKey(
            match_type=archetype["match_type"],
            acos_band=archetype["acos_band"],
            click_volume_band=archetype["click_volume_band"],
            action=str(rec.recommendation_type.value if hasattr(rec.recommendation_type, "value") else rec.recommendation_type),
            strategy_mode=strategy_mode,
        )

        acos_delta = _pct_change(_acos_for(before, target_acos), _acos_for(after, target_acos))
        spend_delta = _pct_change(float(before.spend), float(after.spend))
        succeeded = _outcome_success(before=before, after=after, target_acos=target_acos, action=key.action)

        buckets[key].append(
            {
                "acos_delta_pct": acos_delta,
                "spend_delta_pct": spend_delta,
                "succeeded": 1.0 if succeeded else 0.0,
            }
        )

    out: dict[str, PatternOutcome] = {}
    for key, observations in buckets.items():
        n = len(observations)
        acos_deltas = [o["acos_delta_pct"] for o in observations if o["acos_delta_pct"] is not None]
        spend_deltas = [o["spend_delta_pct"] for o in observations if o["spend_delta_pct"] is not None]
        success = sum(o["succeeded"] for o in observations) / n if n else 0.0

        median_acos = median(acos_deltas) if acos_deltas else None
        median_spend = median(spend_deltas) if spend_deltas else None

        summary = _summary(key=key, n=n, median_acos=median_acos, success=success)
        outcome = PatternOutcome(
            key=key,
            sample_size=n,
            median_acos_delta_pct=median_acos,
            median_spend_delta_pct=median_spend,
            success_rate=success,
            summary=summary,
        )
        out[pattern_key_to_str(key)] = outcome

    return out


def lookup_pattern_for_candidate(
    *,
    pattern_index: dict[str, PatternOutcome],
    snapshot: MonitoringSnapshot,
    action: str,
    strategy_mode: str,
    target_acos: Decimal,
) -> PatternOutcome | None:
    """Find the PatternOutcome that matches a candidate recommendation.

    Returns None when no observations exist for this archetype × action.
    """

    archetype = archetype_for_snapshot(snapshot, target_acos=target_acos)
    key = PatternKey(
        match_type=archetype["match_type"],
        acos_band=archetype["acos_band"],
        click_volume_band=archetype["click_volume_band"],
        action=action,
        strategy_mode=strategy_mode,
    )
    return pattern_index.get(pattern_key_to_str(key))


def pattern_key_to_str(key: PatternKey) -> str:
    return "|".join(
        [
            key.strategy_mode,
            key.action,
            key.match_type,
            key.acos_band,
            key.click_volume_band,
        ]
    )


def _normalize_match_type(match_type: str | None) -> str:
    if not match_type:
        return "unknown"
    value = match_type.strip().lower()
    if value in {"exact", "phrase", "broad", "auto"}:
        return value
    return "other"


def _acos_band(snapshot: MonitoringSnapshot, *, target_acos: Decimal) -> str:
    if snapshot.orders == 0 or snapshot.sales <= 0:
        return "no_orders"
    if snapshot.acos is None:
        return "no_orders"
    target = float(target_acos) if target_acos else 0.5
    if target <= 0:
        target = 0.5
    ratio = float(snapshot.acos) / target
    if ratio < 0.75:
        return "under_target"
    if ratio < 1.1:
        return "near_target"
    if ratio < 2.0:
        return "1-2x_target"
    return "2x+_target"


def _click_band(clicks: int) -> str:
    if clicks >= 100:
        return "high"
    if clicks >= 25:
        return "mid"
    if clicks >= 5:
        return "low"
    return "micro"


def _entity_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join(
        [
            snapshot.campaign_name or "",
            snapshot.ad_group_name or "",
            snapshot.targeting or "",
            snapshot.customer_search_term or "",
            snapshot.match_type or "",
        ]
    )


def _acos_for(snapshot: MonitoringSnapshot, target_acos: Decimal) -> float | None:
    if snapshot.acos is not None:
        return float(snapshot.acos)
    if snapshot.sales <= 0:
        # No-order observations have no defined ACOS; return None so deltas are
        # undefined rather than infinite.
        return None
    return float(snapshot.spend / snapshot.sales)


def _pct_change(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    if before == 0:
        return None
    return ((after - before) / abs(before)) * 100.0


def _outcome_success(
    *,
    before: MonitoringSnapshot,
    after: MonitoringSnapshot,
    target_acos: Decimal,
    action: str,
) -> bool:
    """A pattern observation 'succeeded' if the action moved metrics in the
    intended direction. Definitions are deliberately conservative."""

    target = float(target_acos) if target_acos else 0.5

    if action in {
        RecommendationType.DECREASE_BID.value,
        RecommendationType.ADD_NEGATIVE_EXACT.value,
        RecommendationType.ADD_NEGATIVE_PHRASE.value,
        RecommendationType.PAUSE_REVIEW.value,
    }:
        # Wasted-spend kill actions: success means spend dropped, or ACOS came
        # back inside target.
        if float(after.spend) < float(before.spend) * 0.85:
            return True
        before_acos = _acos_for(before, target_acos)
        after_acos = _acos_for(after, target_acos)
        if after_acos is not None and after_acos <= target:
            return True
        return False

    if action in {RecommendationType.INCREASE_BID.value, RecommendationType.MOVE_TO_EXACT.value}:
        # Scaling actions: success means orders grew without ACOS blowing out.
        if after.orders > before.orders:
            after_acos = _acos_for(after, target_acos)
            if after_acos is None or after_acos <= target * 1.25:
                return True
        return False

    return False


def _summary(*, key: PatternKey, n: int, median_acos: float | None, success: float) -> str:
    pieces = [
        f"action={key.action}",
        f"archetype={key.match_type}/{key.acos_band}/{key.click_volume_band}",
        f"n={n}",
        f"success_rate={success:.0%}",
    ]
    if median_acos is not None:
        sign = "+" if median_acos >= 0 else ""
        pieces.append(f"median_acos_delta={sign}{median_acos:.0f}%")
    return " ".join(pieces)
