from collections import defaultdict
from decimal import Decimal

from apps.api.app.schemas.monitoring import MonitoringSnapshot


MONEY_QUANT = Decimal("0.0001")
RATE_QUANT = Decimal("0.0001")


def snapshot_metrics(snapshot: MonitoringSnapshot, *, report_performance: dict | None = None) -> dict:
    spend = snapshot.spend
    sales = snapshot.sales
    clicks = Decimal(snapshot.clicks)
    impressions = Decimal(snapshot.impressions)
    orders = Decimal(snapshot.orders)
    report_spend = _decimal_from_report(report_performance, "spend")
    report_sales = _decimal_from_report(report_performance, "sales")
    report_clicks = _decimal_from_report(report_performance, "clicks")
    return {
        "impressions": snapshot.impressions,
        "clicks": snapshot.clicks,
        "spend": str(spend),
        "sales": str(sales),
        "orders": snapshot.orders,
        "units": snapshot.units,
        "cpc": _decimal_str(snapshot.cpc or _safe_divide(spend, clicks, MONEY_QUANT)),
        "ctr": _decimal_str(snapshot.ctr or _safe_divide(clicks, impressions, RATE_QUANT)),
        "cvr": _decimal_str(snapshot.cvr or _safe_divide(orders, clicks, RATE_QUANT)),
        "acos": _decimal_str(snapshot.acos or (_safe_divide(spend, sales, RATE_QUANT) if sales > 0 else None)),
        "roas": _decimal_str(snapshot.roas or _safe_divide(sales, spend, RATE_QUANT)),
        "cpa": _decimal_str(_safe_divide(spend, orders, MONEY_QUANT)),
        "spend_per_order": _decimal_str(_safe_divide(spend, orders, MONEY_QUANT)),
        "sales_per_click": _decimal_str(_safe_divide(sales, clicks, MONEY_QUANT)),
        "click_share": _decimal_str(_safe_divide(clicks, report_clicks, RATE_QUANT)),
        "spend_share": _decimal_str(_safe_divide(spend, report_spend, RATE_QUANT)),
        "sales_share": _decimal_str(_safe_divide(sales, report_sales, RATE_QUANT)),
        "zero_order_spend": str(spend if snapshot.orders == 0 else Decimal("0")),
        "wasted_spend": str(spend if snapshot.orders == 0 and spend > 0 else Decimal("0")),
    }


def condition_signals(snapshot: MonitoringSnapshot, *, target_acos: Decimal, default_budget: Decimal, report_performance: dict | None = None) -> dict:
    metrics = snapshot_metrics(snapshot, report_performance=report_performance)
    acos = _decimal_or_none(metrics["acos"])
    roas = _decimal_or_none(metrics["roas"])
    cvr = _decimal_or_none(metrics["cvr"]) or Decimal("0")
    spend = snapshot.spend
    clicks = snapshot.clicks
    orders = snapshot.orders
    match_type = (snapshot.match_type or "").strip().lower()
    return {
        "high_click_zero_order": clicks >= 10 and orders == 0,
        "high_spend_low_sales": spend >= max(default_budget, Decimal("10")) and snapshot.sales <= spend * Decimal("0.50"),
        "low_impression_high_conversion": snapshot.impressions < 100 and orders >= 1 and cvr >= Decimal("0.1500"),
        "strong_converter": orders >= 2 and acos is not None and acos <= target_acos,
        "weak_converter": clicks >= 10 and (orders == 0 or (acos is not None and acos > target_acos * Decimal("1.25"))),
        "under_tested": clicks < 3 or snapshot.impressions < 10,
        "over_tested": clicks >= 20 and orders == 0,
        "budget_pressure": spend >= max(default_budget * Decimal("0.80"), Decimal("8")) and roas is not None and roas >= Decimal("2"),
        "search_term_relevance": _search_term_relevance(snapshot),
        "match_type_risk": "high" if match_type in {"broad", "auto", "-"} else "medium" if match_type == "phrase" else "low",
        "duplicate_overlap": False,
        "broad_match_waste": match_type in {"broad", "auto", "-"} and clicks >= 10 and orders == 0,
        "high_acos": acos is not None and acos > target_acos * Decimal("1.25"),
        "low_roas": roas is not None and roas < _target_roas(target_acos) * Decimal("0.80"),
        "good_conversion_low_impressions": snapshot.impressions < 100 and orders >= 1 and cvr >= Decimal("0.1000"),
    }


def build_performance_rollups(snapshots: list[MonitoringSnapshot]) -> dict:
    groups: dict[str, dict] = {
        "campaign": defaultdict(_empty_accumulator),
        "ad_group": defaultdict(_empty_accumulator),
        "target": defaultdict(_empty_accumulator),
        "search_term": defaultdict(_empty_accumulator),
    }
    report = _empty_accumulator()
    duplicate_terms: dict[str, set[str]] = defaultdict(set)
    duplicate_targets: dict[str, set[str]] = defaultdict(set)
    for snapshot in snapshots:
        duplicate_terms[snapshot.customer_search_term.strip().lower()].add(_target_key(snapshot))
        duplicate_targets[snapshot.targeting.strip().lower()].add(_ad_group_key(snapshot))
        for bucket, key in [
            ("campaign", snapshot.campaign_name),
            ("ad_group", _ad_group_key(snapshot)),
            ("target", _target_key(snapshot)),
            ("search_term", _search_term_key(snapshot)),
        ]:
            _add_snapshot(groups[bucket][key], snapshot)
        _add_snapshot(report, snapshot)
    finalized_report = _finalize_accumulator(report)
    return {
        "campaign": {key: _with_shares(_finalize_accumulator(value), finalized_report) for key, value in groups["campaign"].items()},
        "ad_group": {key: _with_shares(_finalize_accumulator(value), finalized_report) for key, value in groups["ad_group"].items()},
        "target": {key: _with_shares(_finalize_accumulator(value), finalized_report) for key, value in groups["target"].items()},
        "search_term": {key: _with_shares(_finalize_accumulator(value), finalized_report) for key, value in groups["search_term"].items()},
        "report": finalized_report,
        "duplicates": {
            "overlapping_search_terms": sorted(term for term, targets in duplicate_terms.items() if len(targets) > 1),
            "overlapping_targets": sorted(target for target, ad_groups in duplicate_targets.items() if len(ad_groups) > 1),
        },
    }


def search_term_key(snapshot: MonitoringSnapshot) -> str:
    return _search_term_key(snapshot)


def target_key(snapshot: MonitoringSnapshot) -> str:
    return _target_key(snapshot)


def ad_group_key(snapshot: MonitoringSnapshot) -> str:
    return _ad_group_key(snapshot)


def campaign_key(snapshot: MonitoringSnapshot) -> str:
    return snapshot.campaign_name


def _empty_accumulator() -> dict:
    return {"row_count": 0, "impressions": 0, "clicks": 0, "spend": Decimal("0"), "sales": Decimal("0"), "orders": 0, "units": 0}


def _add_snapshot(accumulator: dict, snapshot: MonitoringSnapshot) -> None:
    accumulator["row_count"] += 1
    accumulator["impressions"] += snapshot.impressions
    accumulator["clicks"] += snapshot.clicks
    accumulator["spend"] += snapshot.spend
    accumulator["sales"] += snapshot.sales
    accumulator["orders"] += snapshot.orders
    accumulator["units"] += snapshot.units or 0


def _finalize_accumulator(accumulator: dict) -> dict:
    clicks = Decimal(accumulator["clicks"])
    impressions = Decimal(accumulator["impressions"])
    spend = accumulator["spend"]
    sales = accumulator["sales"]
    orders = Decimal(accumulator["orders"])
    return {
        "row_count": accumulator["row_count"],
        "impressions": accumulator["impressions"],
        "clicks": accumulator["clicks"],
        "spend": str(spend.quantize(MONEY_QUANT)),
        "sales": str(sales.quantize(MONEY_QUANT)),
        "orders": accumulator["orders"],
        "units": accumulator["units"],
        "cpc": _decimal_str(_safe_divide(spend, clicks, MONEY_QUANT)),
        "ctr": _decimal_str(_safe_divide(clicks, impressions, RATE_QUANT)),
        "cvr": _decimal_str(_safe_divide(orders, clicks, RATE_QUANT)),
        "acos": _decimal_str(_safe_divide(spend, sales, RATE_QUANT)) if sales > 0 else None,
        "roas": _decimal_str(_safe_divide(sales, spend, RATE_QUANT)),
        "cpa": _decimal_str(_safe_divide(spend, orders, MONEY_QUANT)),
        "spend_per_order": _decimal_str(_safe_divide(spend, orders, MONEY_QUANT)),
        "sales_per_click": _decimal_str(_safe_divide(sales, clicks, MONEY_QUANT)),
        "zero_order_spend": str((spend if accumulator["orders"] == 0 else Decimal("0")).quantize(MONEY_QUANT)),
        "wasted_spend": str((spend if accumulator["orders"] == 0 and spend > 0 else Decimal("0")).quantize(MONEY_QUANT)),
    }


def _with_shares(metrics: dict, report: dict) -> dict:
    clicks = Decimal(metrics["clicks"])
    spend = Decimal(metrics["spend"])
    sales = Decimal(metrics["sales"])
    return {
        **metrics,
        "click_share": _decimal_str(_safe_divide(clicks, Decimal(report["clicks"]), RATE_QUANT)),
        "spend_share": _decimal_str(_safe_divide(spend, Decimal(report["spend"]), RATE_QUANT)),
        "sales_share": _decimal_str(_safe_divide(sales, Decimal(report["sales"]), RATE_QUANT)),
    }


def _safe_divide(numerator: Decimal, denominator: Decimal, quant: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(quant)


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal_or_none(value: str | int | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _decimal_from_report(report: dict | None, key: str) -> Decimal:
    if not report:
        return Decimal("0")
    return Decimal(str(report.get(key) or "0"))


def _target_roas(target_acos: Decimal) -> Decimal:
    return Decimal("0") if target_acos == 0 else (Decimal("1") / target_acos).quantize(RATE_QUANT)


def _search_term_relevance(snapshot: MonitoringSnapshot) -> str:
    term = snapshot.customer_search_term.strip().lower()
    target = snapshot.targeting.strip().lower()
    if term and term in target:
        return "high"
    if snapshot.orders > 0:
        return "medium"
    if snapshot.clicks >= 10 and snapshot.orders == 0:
        return "low"
    return "unknown"


def _search_term_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([snapshot.campaign_name, snapshot.ad_group_name, snapshot.targeting, snapshot.customer_search_term])


def _target_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([snapshot.campaign_name, snapshot.ad_group_name, snapshot.targeting])


def _ad_group_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([snapshot.campaign_name, snapshot.ad_group_name])
