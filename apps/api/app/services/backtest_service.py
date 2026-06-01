"""Backtest / Simulation Service for AdSurf.

Replays a recommendation against historical monitoring snapshots
to project what would have happened if the recommendation had been
applied N days ago. This builds operator trust by showing
counterfactual outcomes before human approval.

Usage:
    from apps.api.app.services.backtest_service import backtest_recommendation

    result = backtest_recommendation(
        recommendation=rec,
        historical_snapshots=daily_snaps,
        window_days=14,
    )
    # result.projected_acos, result.confidence_interval, etc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from typing import Any

from apps.api.app.schemas.monitoring import (
    Recommendation,
    RecommendationType,
)
from apps.api.app.services.statistical_significance import (
    wilson_lower_bound,
    wilson_upper_bound,
)


@dataclass
class BacktestPoint:
    """Single day in the backtest simulation."""

    day: int  # day offset (1 = first day after approval)
    date: date
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    sales: float = 0.0
    orders: int = 0
    acos: float | None = None
    roas: float | None = None
    cpc: float | None = None
    cvr: float | None = None


@dataclass
class BacktestResult:
    """Projected outcome of applying a recommendation."""

    recommendation_id: str
    recommendation_type: str = ""
    campaign_name: str = ""
    window_days: int = 14

    # Pre-recommendation metrics (from the period before the recommendation)
    pre_spend: float = 0.0
    pre_sales: float = 0.0
    pre_acos: float | None = None
    pre_orders: int = 0
    pre_clicks: int = 0

    # Projected post-recommendation metrics
    projected_spend: float = 0.0
    projected_sales: float = 0.0
    projected_acos: float | None = None
    projected_orders: int = 0
    projected_clicks: int = 0

    # Deltas
    spend_delta_pct: float = 0.0
    sales_delta_pct: float = 0.0
    acos_delta_pct: float = 0.0

    # Confidence
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    confidence_level: float = 0.95  # 95%

    # Simulation metadata
    simulation_method: str = "historical_replay"
    days_with_data: int = 0
    data_quality: str = "adequate"  # adequate | limited | insufficient
    warnings: list[str] = field(default_factory=list)

    # Daily points for charting
    daily_points: list[BacktestPoint] = field(default_factory=list)

    # Summary for UI
    summary: str = ""


def backtest_recommendation(
    *,
    recommendation: Recommendation,
    historical_snapshots: list[dict[str, Any]],
    pre_period_snapshots: list[dict[str, Any]] | None = None,
    window_days: int = 14,
    z_score: float = 1.96,
) -> BacktestResult:
    """Simulate the outcome of a recommendation against historical data.

    Args:
        recommendation: The recommendation to backtest
        historical_snapshots: List of daily snapshots (dict format) covering
            the period AFTER when the recommendation would have been applied.
            Must have keys: date, impressions, clicks, spend, sales, orders, acos, roas
        pre_period_snapshots: Snapshots from BEFORE the recommendation period.
            If not provided, uses recommendation's input_metrics_json.
        window_days: How many days to simulate (default 14)
        z_score: z-score for confidence intervals (1.96 = 95%)

    Returns:
        BacktestResult with projected metrics and confidence intervals
    """
    rec_type = str(recommendation.recommendation_type.value)

    # ── Pre-period metrics ──────────────────────────────────────────
    pre_snaps = pre_period_snapshots or []
    if not pre_snaps:
        # Use the recommendation's own input metrics as the "before" state
        pre_metrics = recommendation.input_metrics_json
        pre_spend = float(pre_metrics.get("spend", 0) or 0)
        pre_sales = float(pre_metrics.get("sales", 0) or 0)
        pre_orders = int(pre_metrics.get("orders", 0) or 0)
        pre_clicks = int(pre_metrics.get("clicks", 0) or 0)
        pre_acos = float(pre_metrics.get("acos", 0) or 0) if pre_spend > 0 else None
    else:
        pre_spend = sum(float(s.get("spend", 0) or 0) for s in pre_snaps)
        pre_sales = sum(float(s.get("sales", 0) or 0) for s in pre_snaps)
        pre_orders = sum(int(s.get("orders", 0) or 0) for s in pre_snaps)
        pre_clicks = sum(int(s.get("clicks", 0) or 0) for s in pre_snaps)
        pre_acos = (pre_spend / pre_sales * 100) if pre_sales > 0 else None

    # ── Post-period simulation ──────────────────────────────────────
    sorted_snaps = sorted(historical_snapshots, key=lambda s: s.get("snapshot_date", s.get("date", "")))
    window_snaps = sorted_snaps[:window_days]

    result = BacktestResult(
        recommendation_id=str(recommendation.id),
        recommendation_type=rec_type,
        campaign_name=recommendation.campaign_name or "",
        window_days=window_days,
        pre_spend=pre_spend,
        pre_sales=pre_sales,
        pre_acos=pre_acos,
        pre_orders=pre_orders,
        pre_clicks=pre_clicks,
        days_with_data=len(window_snaps),
    )

    # ── Build daily points ──────────────────────────────────────────
    daily_points: list[BacktestPoint] = []
    for i, snap in enumerate(window_snaps):
        snap_date = snap.get("snapshot_date") or snap.get("date", "")
        if isinstance(snap_date, str):
            try:
                snap_date = date.fromisoformat(snap_date)
            except ValueError:
                snap_date = date.today() + timedelta(days=i)

        spend = float(snap.get("spend", 0) or 0)
        sales = float(snap.get("sales", 0) or 0)
        orders = int(snap.get("orders", 0) or 0)
        clicks = int(snap.get("clicks", 0) or 0)
        impressions = int(snap.get("impressions", 0) or 0)

        daily_points.append(
            BacktestPoint(
                day=i + 1,
                date=snap_date if isinstance(snap_date, date) else date.today(),
                impressions=impressions,
                clicks=clicks,
                spend=spend,
                sales=sales,
                orders=orders,
                acos=(spend / sales * 100) if sales > 0 else None,
                roas=(sales / spend) if spend > 0 else None,
                cpc=(spend / clicks) if clicks > 0 else None,
                cvr=(orders / clicks * 100) if clicks > 0 else None,
            )
        )

    result.daily_points = daily_points

    # ── Projected totals ────────────────────────────────────────────
    projected_spend = sum(p.spend for p in daily_points)
    projected_sales = sum(p.sales for p in daily_points)
    projected_orders = sum(p.orders for p in daily_points)
    projected_clicks = sum(p.clicks for p in daily_points)

    result.projected_spend = projected_spend
    result.projected_sales = projected_sales
    result.projected_orders = projected_orders
    result.projected_clicks = projected_clicks
    result.projected_acos = (projected_spend / projected_sales * 100) if projected_sales > 0 else None

    # ── Deltas ──────────────────────────────────────────────────────
    if pre_spend > 0:
        result.spend_delta_pct = ((projected_spend - pre_spend) / pre_spend) * 100
    if pre_sales > 0:
        result.sales_delta_pct = ((projected_sales - pre_sales) / pre_sales) * 100
    if result.projected_acos is not None and pre_acos is not None and pre_acos > 0:
        result.acos_delta_pct = ((result.projected_acos - pre_acos) / pre_acos) * 100

    # ── Confidence interval on projected ACOS ───────────────────────
    if projected_clicks > 0 and projected_orders > 0:
        result.confidence_interval_low = wilson_lower_bound(
            projected_orders, projected_clicks, z=z_score
        )
        result.confidence_interval_high = wilson_upper_bound(
            projected_orders, projected_clicks, z=z_score
        )

    # ── Data quality assessment ─────────────────────────────────────
    if len(window_snaps) < 7:
        result.data_quality = "insufficient"
        result.warnings.append(f"Only {len(window_snaps)} days of data available; need at least 7 for reliable backtest.")
    elif len(window_snaps) < 14:
        result.data_quality = "limited"
        result.warnings.append(f"Only {len(window_snaps)} days of data; 14+ recommended for confidence.")

    if projected_clicks < 10:
        result.warnings.append(f"Fewer than 10 projected clicks ({projected_clicks}) — confidence is low.")
    if projected_orders == 0:
        result.warnings.append("Zero orders in projection period — impact uncertain.")

    # ── Generate summary ────────────────────────────────────────────
    result.summary = _generate_summary(result, rec_type)

    return result


def _generate_summary(result: BacktestResult, rec_type: str) -> str:
    """Generate a human-readable backtest summary for the approval UI."""

    if result.data_quality == "insufficient":
        return (
            f"Not enough historical data to reliably project the impact of this "
            f"'{rec_type}' recommendation. {result.days_with_data} days of data available "
            f"({result.window_days} needed). Consider waiting for more data before deciding."
        )

    acos_str = (
        f"{result.projected_acos:.1f}%" if result.projected_acos is not None else "unknown"
    )

    delta_str = ""
    if result.acos_delta_pct != 0:
        direction = "lower" if result.acos_delta_pct < 0 else "higher"
        delta_str = f" ({abs(result.acos_delta_pct):.1f}% {direction} than before)"

    spend_delta_str = ""
    if result.spend_delta_pct != 0:
        spend_delta_str = (
            f"Spend would be {abs(result.spend_delta_pct):.0f}% "
            f"{'lower' if result.spend_delta_pct < 0 else 'higher'}."
        )

    ci_str = ""
    if result.confidence_interval_low is not None:
        ci_str = (
            f" 95% confidence CVR range: "
            f"{result.confidence_interval_low:.2%} – {result.confidence_interval_high:.2%}."
        )

    return (
        f"If this '{rec_type}' recommendation had been applied "
        f"{result.window_days} days ago, projected ACOS would be {acos_str}{delta_str}. "
        f"{spend_delta_str}{ci_str}"
        f" Based on {result.days_with_data} days of historical data."
    )


def project_recommendation_impact(
    *,
    recommendation: Recommendation,
    daily_snapshots: list[dict[str, Any]],
    window_days: int = 14,
) -> dict[str, Any]:
    """Convenience wrapper that returns a dict suitable for the API/UI."""
    result = backtest_recommendation(
        recommendation=recommendation,
        historical_snapshots=daily_snapshots,
        window_days=window_days,
    )
    return {
        "recommendation_id": result.recommendation_id,
        "recommendation_type": result.recommendation_type,
        "campaign_name": result.campaign_name,
        "window_days": result.window_days,
        "pre": {
            "spend": result.pre_spend,
            "sales": result.pre_sales,
            "acos": result.pre_acos,
            "orders": result.pre_orders,
            "clicks": result.pre_clicks,
        },
        "projected": {
            "spend": result.projected_spend,
            "sales": result.projected_sales,
            "acos": result.projected_acos,
            "orders": result.projected_orders,
            "clicks": result.projected_clicks,
        },
        "deltas": {
            "spend_pct": result.spend_delta_pct,
            "sales_pct": result.sales_delta_pct,
            "acos_pct": result.acos_delta_pct,
        },
        "confidence": {
            "cvr_interval_low": result.confidence_interval_low,
            "cvr_interval_high": result.confidence_interval_high,
            "level": result.confidence_level,
        },
        "data_quality": result.data_quality,
        "days_with_data": result.days_with_data,
        "warnings": result.warnings,
        "summary": result.summary,
        "daily_points": [
            {
                "day": p.day,
                "date": p.date.isoformat() if isinstance(p.date, date) else str(p.date),
                "impressions": p.impressions,
                "clicks": p.clicks,
                "spend": p.spend,
                "sales": p.sales,
                "orders": p.orders,
                "acos": p.acos,
                "roas": p.roas,
                "cpc": p.cpc,
                "cvr": p.cvr,
            }
            for p in result.daily_points
        ],
    }