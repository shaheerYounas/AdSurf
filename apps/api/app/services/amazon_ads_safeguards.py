"""Deterministic Amazon Ads upload safeguards.

These checks turn raw Sponsored Products report hazards into reviewable
warnings. They never recommend or execute live Amazon Ads changes.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from apps.api.app.schemas.account_imports import ReportType
from apps.api.app.services.report_type_detector import ReportDetectionResult


SAFE = "safe"
NEEDS_REVIEW = "needs_review"
HIGH_RISK = "high_risk"
NOT_ENOUGH_DATA = "not_enough_data"
POSSIBLE_DUPLICATE = "possible_duplicate"
POSSIBLE_ASIN_TARGETING = "possible_asin_targeting"
POSSIBLE_BRANDED_TERM = "possible_branded_term"
POSSIBLE_IRRELEVANT_TERM = "possible_irrelevant_term"
ZERO_SALES_SPEND = "zero_sales_spend"
MARGIN_RISK = "margin_risk"

ASIN_PATTERN = re.compile(r"^b[0-9a-z]{9}$", re.IGNORECASE)
AUTO_TARGETING_VALUES = {
    "substitutes",
    "close match",
    "loose match",
    "complements",
    "keyword-group",
    "keyword group",
}
METRIC_TOLERANCE = Decimal("0.0100")
NUMERIC_COLUMNS = {
    "impressions",
    "clicks",
    "spend",
    "cost per click cpc",
    "sales",
    "7 day total sales",
    "14 day total sales",
    "orders",
    "7 day total orders",
    "14 day total orders",
    "7 day total orders number",
    "14 day total orders number",
    "7 day total units",
    "7 day advertised sku sales",
    "7 day other sku sales",
    "total return on advertising spend roas",
}
PERCENT_COLUMNS = {
    "acos",
    "total advertising cost of sales acos",
    "click thru rate ctr",
    "clickthru rate ctr",
    "conversion rate",
    "7 day conversion rate",
}
HEADER_ALIASES = {
    "cost": "spend",
    "search term": "customer search term",
    "7 day total sales": "sales",
    "14 day total sales": "sales",
    "7 day total orders": "orders",
    "14 day total orders": "orders",
    "7 day total orders number": "orders",
    "14 day total orders number": "orders",
    "clickthru rate ctr": "click thru rate ctr",
    "total advertising cost of sales acos": "acos",
    "total return on advertising spend roas": "roas",
    "7 day conversion rate": "conversion rate",
}


@dataclass
class SafeguardResult:
    warnings: list[dict] = field(default_factory=list)
    risk_labels: list[str] = field(default_factory=list)

    def add(self, *, code: str, message: str, label: str = NEEDS_REVIEW, row_number: int | None = None, details: dict | None = None) -> None:
        payload = {"code": code, "message": message, "risk_label": label}
        if row_number is not None:
            payload["row_number"] = row_number
        if details:
            payload["details"] = details
        self.warnings.append(payload)
        if label not in self.risk_labels:
            self.risk_labels.append(label)


def analyze_search_term_report_rows(
    *,
    rows: list[dict],
    detection: ReportDetectionResult,
    expected_currency: str | None = "USD",
    expected_country: str | None = "United States",
) -> SafeguardResult:
    result = SafeguardResult()
    if detection.detected_report_type != ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT:
        result.add(
            code="REPORT_TYPE_REVIEW_REQUIRED",
            message="Uploaded report is not confidently detected as a Sponsored Products Search Term Report.",
            label=HIGH_RISK,
            details={"detected_report_type": detection.detected_report_type.value, "confidence": detection.confidence.value},
        )
    if not detection.required_columns_present:
        result.add(
            code="REQUIRED_COLUMNS_MISSING",
            message="Required report columns are missing; metric and optimization analysis must not proceed blindly.",
            label=HIGH_RISK,
            details={"missing_columns": detection.missing_columns},
        )

    currencies: set[str] = set()
    countries: set[str] = set()
    retailers: set[str] = set()
    duplicate_term_contexts: dict[str, set[str]] = defaultdict(set)
    exact_row_occurrences: dict[str, list[int]] = defaultdict(list)
    attribution_windows: set[str] = set()
    date_ranges: set[tuple[str, str]] = set()
    asin_search_terms = 0
    keyword_search_terms = 0
    low_data_rows = 0

    for index, row in enumerate(rows, start=2):
        if index == 2:
            _validate_header_shape(row, result)
        normalized = _normalize_row(row)
        row_number = int(row.get("_row_number", index) or index)
        exact_row_occurrences[_row_signature(normalized)].append(row_number)
        currency = _text(normalized, "currency")
        country = _text(normalized, "country")
        retailer = _text(normalized, "retailer")
        if currency:
            currencies.add(currency.upper())
        if country:
            countries.add(country.lower())
        if retailer:
            retailers.add(retailer.lower())

        _collect_attribution_windows(normalized, attribution_windows)
        _collect_date_range(normalized, date_ranges)
        _validate_numeric_columns(normalized, result, row_number)
        _validate_percentage_columns(normalized, result, row_number)
        _validate_non_negative_metrics(normalized, result, row_number)
        _validate_metric_formulas(normalized, result, row_number)
        term_kind = _classify_search_term(normalized, result, row_number)
        if term_kind == "asin":
            asin_search_terms += 1
        elif term_kind == "keyword":
            keyword_search_terms += 1
        _validate_sales_columns(normalized, result, row_number)
        _validate_date_range(normalized, result, row_number)
        if _validate_data_reliability(normalized, result, row_number):
            low_data_rows += 1

        term = (_text(normalized, "customer search term") or _text(normalized, "search term") or "").lower()
        if term:
            context = "|".join(
                [
                    _text(normalized, "campaign name") or "",
                    _text(normalized, "ad group name") or "",
                    _text(normalized, "targeting") or "",
                    _text(normalized, "match type") or "",
                    _text(normalized, "asin") or _text(normalized, "advertised asin") or "",
                    _text(normalized, "sku") or _text(normalized, "advertised sku") or "",
                ]
            ).lower()
            duplicate_term_contexts[term].add(context)

    if expected_currency and currencies and ({expected_currency.upper()} != currencies):
        result.add(
            code="CURRENCY_MISMATCH",
            message="Report currency does not match the expected workspace/product currency.",
            label=HIGH_RISK,
            details={"expected_currency": expected_currency, "observed_currencies": sorted(currencies)},
        )
    if len(currencies) > 1:
        result.add(code="MIXED_CURRENCIES", message="Multiple currencies appear in one report.", label=HIGH_RISK, details={"currencies": sorted(currencies)})
    if expected_country and countries and {expected_country.lower()} != countries:
        result.add(
            code="MARKETPLACE_MISMATCH",
            message="Report country does not match the expected marketplace.",
            label=HIGH_RISK,
            details={"expected_country": expected_country, "observed_countries": sorted(countries)},
        )
    if len(countries) > 1:
        result.add(code="MIXED_MARKETPLACES", message="Multiple countries appear in one report.", label=HIGH_RISK, details={"countries": sorted(countries)})
    if retailers and retailers != {"amazon"}:
        result.add(code="RETAILER_REVIEW_REQUIRED", message="Report retailer is not consistently Amazon.", label=NEEDS_REVIEW, details={"retailers": sorted(retailers)})
    if len(attribution_windows) > 1:
        result.add(
            code="MIXED_ATTRIBUTION_WINDOWS",
            message="Report contains both 7-day and 14-day attribution metrics; do not compare them as the same metric.",
            label=NEEDS_REVIEW,
            details={"windows": sorted(attribution_windows)},
        )
    if len(date_ranges) > 1:
        result.add(
            code="MIXED_DATE_RANGES",
            message="Rows contain multiple date ranges; optimization should verify the intended reporting window.",
            label=NEEDS_REVIEW,
            details={"date_ranges": [{"start_date": start, "end_date": end} for start, end in sorted(date_ranges)[:25]]},
        )

    duplicate_terms = sorted(term for term, contexts in duplicate_term_contexts.items() if len(contexts) > 1)
    if duplicate_terms:
        result.add(
            code="DUPLICATE_SEARCH_TERM_CONTEXTS",
            message="The same search term appears in multiple campaign/ad group/target/match/product contexts.",
            label=POSSIBLE_DUPLICATE,
            details={"search_terms": duplicate_terms[:25], "duplicate_count": len(duplicate_terms)},
        )
    duplicate_rows = [row_numbers for row_numbers in exact_row_occurrences.values() if len(row_numbers) > 1]
    if duplicate_rows:
        result.add(
            code="DUPLICATE_REPORT_ROWS",
            message="Identical report rows appear more than once.",
            label=POSSIBLE_DUPLICATE,
            details={"duplicate_row_groups": duplicate_rows[:25], "duplicate_group_count": len(duplicate_rows)},
        )
    if asin_search_terms and keyword_search_terms:
        result.add(
            code="MIXED_ASIN_AND_KEYWORD_SEARCH_TERMS",
            message="Search term rows include both ASIN-like product terms and keyword text; separate product-targeting review from keyword optimization.",
            label=NEEDS_REVIEW,
            details={"asin_like_rows": asin_search_terms, "keyword_like_rows": keyword_search_terms},
        )
    if rows and low_data_rows / len(rows) >= 0.50:
        result.add(
            code="OPTIMIZATION_DATA_INSUFFICIENT",
            message="Most rows have too little click/order evidence for confident optimization decisions.",
            label=NOT_ENOUGH_DATA,
            details={"low_data_rows": low_data_rows, "total_rows": len(rows)},
        )
    if not rows:
        result.add(code="OPTIMIZATION_DATA_INSUFFICIENT", message="Report has no parsed rows available for optimization.", label=HIGH_RISK)

    if not result.risk_labels:
        result.risk_labels.append(SAFE)
    return result


def _validate_header_shape(row: dict, result: SafeguardResult) -> None:
    hidden_space_headers = [str(key) for key in row if not str(key).startswith("_") and str(key) != str(key).strip()]
    if hidden_space_headers:
        result.add(
            code="HEADER_HIDDEN_SPACES_NORMALIZED",
            message="Column names contain leading or trailing spaces; headers were normalized before analysis.",
            label=NEEDS_REVIEW,
            details={"headers": hidden_space_headers[:25]},
        )
    aliases = []
    for key in row:
        if str(key).startswith("_"):
            continue
        normalized = _normalize_header(str(key))
        canonical = HEADER_ALIASES.get(normalized)
        if canonical and canonical != normalized:
            aliases.append({"observed": str(key), "canonical": canonical})
    if aliases:
        result.add(
            code="COLUMN_NAME_ALIASES_NORMALIZED",
            message="Report uses known Amazon column-name variants; aliases were mapped to canonical metrics.",
            label=NEEDS_REVIEW,
            details={"aliases": aliases[:25]},
        )


def _normalize_row(row: dict) -> dict:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if str(key).startswith("_"):
            continue
        normalized[_normalize_header(str(key))] = value
    _alias(normalized, "search term", "customer search term")
    _alias(normalized, "cost", "spend")
    _alias(normalized, "7 day total sales", "sales")
    _alias(normalized, "14 day total sales", "sales")
    _alias(normalized, "7 day total orders", "orders")
    _alias(normalized, "14 day total orders", "orders")
    _alias(normalized, "7 day total orders number", "orders")
    _alias(normalized, "14 day total orders number", "orders")
    _alias(normalized, "clickthru rate ctr", "click thru rate ctr")
    _alias(normalized, "total advertising cost of sales acos", "acos")
    _alias(normalized, "total return on advertising spend roas", "roas")
    _alias(normalized, "7 day conversion rate", "conversion rate")
    return normalized


def _row_signature(row: dict) -> str:
    values = {key: _signature_value(value) for key, value in row.items() if not key.startswith("_")}
    return repr(sorted(values.items()))


def _signature_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower()


def _alias(row: dict, source: str, target: str) -> None:
    if source in row and target not in row:
        row[target] = row[source]


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


def _text(row: dict, key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(row: dict, key: str, *, percent: bool = False) -> Decimal | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    text = str(value).strip()
    is_percent = text.endswith("%")
    cleaned = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    return number / Decimal("100") if percent and is_percent else number


def _metric(row: dict, key: str) -> Decimal:
    return _decimal(row, key) or Decimal("0")


def _validate_numeric_columns(row: dict, result: SafeguardResult, row_number: int) -> None:
    for key in sorted(NUMERIC_COLUMNS):
        if key in row and _text(row, key) is not None and _decimal(row, key) is None:
            result.add(
                code="NUMERIC_COLUMN_NOT_NUMERIC",
                message=f"Metric '{key}' must contain numeric values.",
                label=HIGH_RISK,
                row_number=row_number,
                details={"metric": key, "value": str(row.get(key))},
            )


def _validate_percentage_columns(row: dict, result: SafeguardResult, row_number: int) -> None:
    for key in sorted(PERCENT_COLUMNS):
        text = _text(row, key)
        if text is None:
            continue
        observed = _decimal(row, key, percent=True)
        if observed is None:
            result.add(
                code="PERCENT_COLUMN_NOT_NUMERIC",
                message=f"Percentage metric '{key}' must be a decimal like 0.25 or a percent string like 25%.",
                label=HIGH_RISK,
                row_number=row_number,
                details={"metric": key, "value": text},
            )
            continue
        if not text.endswith("%") and observed > 1:
            result.add(
                code="PERCENT_FORMAT_AMBIGUOUS",
                message=f"Percentage metric '{key}' is greater than 1 without a percent sign; review whether it means {text}% or {text}x.",
                label=NEEDS_REVIEW,
                row_number=row_number,
                details={"metric": key, "value": text},
            )


def _validate_non_negative_metrics(row: dict, result: SafeguardResult, row_number: int) -> None:
    for key in ("impressions", "clicks", "spend", "sales", "orders", "7 day total units", "7 day advertised sku sales", "7 day other sku sales"):
        value = _decimal(row, key)
        if value is not None and value < 0:
            result.add(code="NEGATIVE_METRIC_VALUE", message=f"Metric '{key}' cannot be negative.", label=HIGH_RISK, row_number=row_number, details={"metric": key, "value": str(value)})


def _validate_metric_formulas(row: dict, result: SafeguardResult, row_number: int) -> None:
    impressions = _metric(row, "impressions")
    clicks = _metric(row, "clicks")
    spend = _metric(row, "spend")
    sales = _metric(row, "sales")
    orders = _metric(row, "orders")
    if clicks > impressions and impressions >= 0:
        result.add(code="CLICKS_EXCEED_IMPRESSIONS", message="Clicks exceed impressions.", label=HIGH_RISK, row_number=row_number)
    if orders > clicks and clicks >= 0:
        result.add(code="ORDERS_EXCEED_CLICKS", message="Orders exceed clicks.", label=HIGH_RISK, row_number=row_number)
    if spend > 0 and clicks == 0:
        result.add(code="SPEND_WITHOUT_CLICKS", message="Spend exists without clicks.", label=HIGH_RISK, row_number=row_number)
    if sales > 0 and orders == 0:
        result.add(code="SALES_WITHOUT_ORDERS", message="Sales exist without orders.", label=HIGH_RISK, row_number=row_number)
    if spend > 0 and sales == 0:
        result.add(code="SPEND_WITH_NO_SALES", message="Spend with zero sales must not be treated as good ACOS.", label=ZERO_SALES_SPEND, row_number=row_number)

    _compare_metric(row, result, row_number, "cost per click cpc", _divide(spend, clicks), "CPC_MISMATCH", "CPC should equal Spend / Clicks.")
    _compare_metric(row, result, row_number, "click thru rate ctr", _divide(clicks, impressions), "CTR_MISMATCH", "CTR should equal Clicks / Impressions.", percent=True)
    _compare_metric(row, result, row_number, "conversion rate", _divide(orders, clicks), "CVR_MISMATCH", "Conversion rate should equal Orders / Clicks.", percent=True)
    if sales > 0:
        _compare_metric(row, result, row_number, "acos", _divide(spend, sales), "ACOS_MISMATCH", "ACOS should equal Spend / Sales.", percent=True)
    elif _text(row, "acos"):
        result.add(code="ACOS_PRESENT_WITH_ZERO_SALES", message="ACOS is present even though sales are zero; review the report value.", label=HIGH_RISK, row_number=row_number)
    elif spend > 0:
        result.add(code="BLANK_ACOS_WITH_ZERO_SALES_HANDLED", message="ACOS is blank because sales are zero; treat this as zero-sales spend, not efficient performance.", label=ZERO_SALES_SPEND, row_number=row_number)
    _compare_metric(row, result, row_number, "roas", _divide(sales, spend), "ROAS_MISMATCH", "ROAS should equal Sales / Spend.")


def _compare_metric(row: dict, result: SafeguardResult, row_number: int, key: str, expected: Decimal | None, code: str, message: str, *, percent: bool = False) -> None:
    observed = _decimal(row, key, percent=percent)
    if observed is None or expected is None:
        return
    if abs(observed - expected) > METRIC_TOLERANCE:
        result.add(
            code=code,
            message=message,
            label=NEEDS_REVIEW,
            row_number=row_number,
            details={"observed": str(observed), "recalculated": str(expected.quantize(Decimal("0.0001")))},
        )


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _classify_search_term(row: dict, result: SafeguardResult, row_number: int) -> str | None:
    term = (_text(row, "customer search term") or "").strip()
    targeting = (_text(row, "targeting") or "").strip().lower()
    match_type = (_text(row, "match type") or "").strip().lower()
    term_kind = None
    if term and ASIN_PATTERN.match(term):
        result.add(code="ASIN_SEARCH_TERM", message="Customer search term looks like an ASIN; review as product targeting, not keyword text.", label=POSSIBLE_ASIN_TARGETING, row_number=row_number, details={"search_term": term})
        term_kind = "asin"
    elif term:
        term_kind = "keyword"
    if targeting in AUTO_TARGETING_VALUES or targeting.startswith("asin="):
        result.add(code="AUTO_OR_PRODUCT_TARGETING_CONTEXT", message="Targeting context appears to be auto or product targeting; keyword rules may not apply directly.", label=NEEDS_REVIEW, row_number=row_number, details={"targeting": targeting})
    if match_type in {"", "-"}:
        result.add(code="MATCH_TYPE_UNSPECIFIED", message="Match type is missing or '-', so auto/product-targeting logic must be reviewed.", label=NEEDS_REVIEW, row_number=row_number)
    return term_kind


def _validate_sales_columns(row: dict, result: SafeguardResult, row_number: int) -> None:
    total_sales = _metric(row, "sales")
    advertised_sales = _metric(row, "7 day advertised sku sales")
    other_sales = _metric(row, "7 day other sku sales")
    orders = _metric(row, "orders")
    units = _decimal(row, "7 day total units")
    if units is not None and orders > 0 and units != orders:
        result.add(code="ORDERS_UNITS_DIVERGE", message="Orders and units differ; do not treat units as orders.", label=NEEDS_REVIEW, row_number=row_number, details={"orders": str(orders), "units": str(units)})
    if total_sales > 0 and other_sales > advertised_sales and other_sales / total_sales >= Decimal("0.50"):
        result.add(code="OTHER_SKU_SALES_DOMINATE", message="Other-SKU sales dominate this row; review product fit before scaling.", label=NEEDS_REVIEW, row_number=row_number, details={"total_sales": str(total_sales), "advertised_sku_sales": str(advertised_sales), "other_sku_sales": str(other_sales)})


def _validate_date_range(row: dict, result: SafeguardResult, row_number: int) -> None:
    start = _text(row, "start date")
    end = _text(row, "end date")
    if start and re.fullmatch(r"\d+(\.\d+)?", start):
        result.add(code="START_DATE_SERIAL_NOT_CONVERTED", message="Start Date still looks like an Excel serial number.", label=HIGH_RISK, row_number=row_number)
    if end and re.fullmatch(r"\d+(\.\d+)?", end):
        result.add(code="END_DATE_SERIAL_NOT_CONVERTED", message="End Date still looks like an Excel serial number.", label=HIGH_RISK, row_number=row_number)
    parsed_start = _date_sort_key(start)
    parsed_end = _date_sort_key(end)
    if start and parsed_start is None:
        result.add(code="START_DATE_INVALID", message="Start Date could not be parsed as a supported report date.", label=HIGH_RISK, row_number=row_number, details={"start_date": start})
    if end and parsed_end is None:
        result.add(code="END_DATE_INVALID", message="End Date could not be parsed as a supported report date.", label=HIGH_RISK, row_number=row_number, details={"end_date": end})
    if parsed_start and parsed_end and parsed_start > parsed_end:
        result.add(code="DATE_RANGE_INVALID", message="Start Date is after End Date.", label=HIGH_RISK, row_number=row_number, details={"start_date": start, "end_date": end})


def _validate_data_reliability(row: dict, result: SafeguardResult, row_number: int) -> bool:
    clicks = _metric(row, "clicks")
    spend = _metric(row, "spend")
    orders = _metric(row, "orders")
    sales = _metric(row, "sales")
    acos = _divide(spend, sales) if sales > 0 else None
    low_data = False
    if clicks < 3 and orders <= 1:
        result.add(code="NOT_ENOUGH_DATA", message="Row has too little click/order data for confident optimization.", label=NOT_ENOUGH_DATA, row_number=row_number)
        low_data = True
    if clicks >= 10 and orders == 0:
        result.add(code="HIGH_CLICK_ZERO_ORDER", message="Search term has clicks but no orders.", label=ZERO_SALES_SPEND, row_number=row_number)
    if acos is not None and acos >= Decimal("0.50"):
        result.add(code="MARGIN_RISK_DEFAULT_ACOS", message="ACOS is at or above the default 50% target; verify break-even margin before scaling.", label=MARGIN_RISK, row_number=row_number, details={"acos": str(acos.quantize(Decimal("0.0001")))})
    return low_data


def _collect_attribution_windows(row: dict, windows: set[str]) -> None:
    for key in row:
        if key.startswith("7 day "):
            windows.add("7_day")
        if key.startswith("14 day "):
            windows.add("14_day")


def _collect_date_range(row: dict, ranges: set[tuple[str, str]]) -> None:
    start = _text(row, "start date")
    end = _text(row, "end date")
    if start and end:
        ranges.add((start, end))


def _date_sort_key(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    stripped = value.strip()
    patterns = [
        r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})",
        r"(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})",
        r"(?P<month>\d{1,2})-(?P<day>\d{1,2})-(?P<year>\d{4})",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, stripped)
        if match:
            year = int(match.group("year"))
            month = int(match.group("month"))
            day = int(match.group("day"))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return (year, month, day)
    return None
