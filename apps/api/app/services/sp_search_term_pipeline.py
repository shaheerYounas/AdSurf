"""SP Search Term report parser, validator, normalizer, and aggregator pipeline.

Consumes rows already parsed by UploadParser (row_data_json dicts) and produces:
  - A validated row list (typed, classified, cross-field checked)
  - An aggregated row list (grouped by 5 dimensions, metrics recalculated from totals)
  - A validation report (health summary for UI and recommendation gate)

Design constraints:
  - Pure service: no DB, no HTTP, no side effects.
  - All metrics recalculated from raw totals — never averaged from percentages.
  - Recommendations gated behind schema validity (missing required cols = blocked).
  - Row warnings do NOT block recommendations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Header normalization
# ---------------------------------------------------------------------------

_NORM_RE = re.compile(r"[^a-z0-9]+")

_ASIN_RE = re.compile(r"^B[0-9A-Z]{9}$")
_NUMERIC_ASIN_RE = re.compile(r"^[0-9]{10}$")
_CURRENCY_PREFIX_RE = re.compile(r"^[£$€¥₹₩]+\s*")

RATIO_TOLERANCE = Decimal("0.10")  # 10% relative tolerance for cross-field validation


def _norm_key(header: str) -> str:
    """Lower + collapse non-alphanumeric → space + strip. Used for header lookup."""
    return _NORM_RE.sub(" ", header.strip().lower()).strip()


# ---------------------------------------------------------------------------
# Column map: normalized header key → canonical field name
# Handles Amazon's verbose column names including parenthetical suffixes.
# ---------------------------------------------------------------------------

SP_COLUMN_MAP: dict[str, str] = {
    # Identity / dimension fields
    "start date": "start_date",
    "end date": "end_date",
    "portfolio name": "portfolio_name",
    "currency": "currency",
    "campaign name": "campaign_name",
    "ad group name": "ad_group_name",
    "retailer": "retailer",
    "country": "country",
    "targeting": "targeting",
    "match type": "match_type",
    "customer search term": "customer_search_term",
    # Core count metrics
    "impressions": "impressions",
    "clicks": "clicks",
    # Rate metrics (Amazon reports as % numbers in CSV, fractions in XLSX)
    "click thru rate ctr": "ctr",               # "Click-Thru Rate (CTR)"
    "click through rate ctr": "ctr",             # alternate
    # CPC
    "cost per click cpc": "cpc",                 # "Cost Per Click (CPC)"
    # Money metrics
    "spend": "spend",
    "7 day total sales": "total_sales",
    "7 day advertised sku sales": "advertised_sku_sales",
    "7 day other sku sales": "other_sku_sales",
    # Derived rate metrics
    "total advertising cost of sales acos": "acos",       # "Total Advertising Cost of Sales (ACOS)"
    "total return on advertising spend roas": "roas",     # "Total Return on Advertising Spend (ROAS)"
    "7 day conversion rate": "conversion_rate",
    # Count metrics
    "7 day total orders": "total_orders",
    "7 day total units": "total_units",
    "7 day advertised sku units": "advertised_sku_units",
    "7 day other sku units": "other_sku_units",
}

# Canonical field names that are required for schema validation
REQUIRED_CANONICAL: frozenset[str] = frozenset({
    "campaign_name",
    "ad_group_name",
    "targeting",
    "match_type",
    "customer_search_term",
    "impressions",
    "clicks",
    "spend",
    "total_sales",
    "total_orders",
})

# Fields whose canonical name must be present for identity; used to quarantine rows
REQUIRED_IDENTITY: frozenset[str] = frozenset({
    "campaign_name",
    "ad_group_name",
    "targeting",
    "customer_search_term",
})

_SUMMARY_PATTERNS: tuple[str, ...] = ("total", "subtotal", "grand total", "summary", "row total")
_AUTO_TARGETING_VALUES: frozenset[str] = frozenset({
    "*", "auto",
    "close match", "close-match",   # Amazon uses both hyphenated and space variants
    "loose match", "loose-match",
    "substitutes", "complements",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class RowSeverity(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class RowIssue:
    field: str
    code: str
    message: str
    severity: RowSeverity


@dataclass
class SPNormalizedRow:
    row_number: int
    raw_data: dict       # exact dict from UploadParser (keys = stripped-but-not-lowercased headers)
    # typed canonical fields
    start_date: date | None = None
    end_date: date | None = None
    portfolio_name: str | None = None
    currency: str | None = None
    campaign_name: str | None = None
    ad_group_name: str | None = None
    retailer: str | None = None
    country: str | None = None
    targeting: str | None = None
    match_type: str | None = None
    customer_search_term: str | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    spend: Decimal | None = None
    total_sales: Decimal | None = None
    acos: Decimal | None = None
    roas: Decimal | None = None
    total_orders: int | None = None
    total_units: int | None = None
    conversion_rate: Decimal | None = None
    advertised_sku_units: int | None = None
    other_sku_units: int | None = None
    advertised_sku_sales: Decimal | None = None
    other_sku_sales: Decimal | None = None
    # classification
    search_term_type: str | None = None     # "asin" | "keyword"
    targeting_type: str | None = None       # "auto" | "product_asin" | "category" | "keyword"


@dataclass
class SPValidatedRow:
    normalized: SPNormalizedRow
    issues: list[RowIssue] = field(default_factory=list)
    is_quarantined: bool = False

    @property
    def effective_severity(self) -> RowSeverity:
        if self.is_quarantined:
            return RowSeverity.QUARANTINED
        severities = {i.severity for i in self.issues}
        if RowSeverity.ERROR in severities:
            return RowSeverity.ERROR
        if RowSeverity.WARNING in severities:
            return RowSeverity.WARNING
        return RowSeverity.OK


@dataclass
class SPAggregatedRow:
    campaign_name: str
    ad_group_name: str
    targeting: str
    customer_search_term: str
    match_type: str
    row_count: int = 0
    total_impressions: int = 0
    total_clicks: int = 0
    total_spend: Decimal = field(default_factory=lambda: Decimal(0))
    total_sales: Decimal = field(default_factory=lambda: Decimal(0))
    total_orders: int = 0
    total_units: int = 0
    # recalculated from totals — never averaged row percentages
    agg_ctr: Decimal | None = None
    agg_cpc: Decimal | None = None
    agg_acos: Decimal | None = None
    agg_roas: Decimal | None = None
    agg_cvr: Decimal | None = None
    search_term_type: str | None = None
    targeting_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    currency: str | None = None

    def as_dict(self) -> dict:
        return {
            "campaign_name": self.campaign_name,
            "ad_group_name": self.ad_group_name,
            "targeting": self.targeting,
            "customer_search_term": self.customer_search_term,
            "match_type": self.match_type,
            "row_count": self.row_count,
            "total_impressions": self.total_impressions,
            "total_clicks": self.total_clicks,
            "total_spend": str(self.total_spend),
            "total_sales": str(self.total_sales),
            "total_orders": self.total_orders,
            "total_units": self.total_units,
            "agg_ctr": str(self.agg_ctr) if self.agg_ctr is not None else None,
            "agg_cpc": str(self.agg_cpc) if self.agg_cpc is not None else None,
            "agg_acos": str(self.agg_acos) if self.agg_acos is not None else None,
            "agg_roas": str(self.agg_roas) if self.agg_roas is not None else None,
            "agg_cvr": str(self.agg_cvr) if self.agg_cvr is not None else None,
            "search_term_type": self.search_term_type,
            "targeting_type": self.targeting_type,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "currency": self.currency,
        }


@dataclass
class SPSchemaResult:
    mapped_headers: dict[str, str]  # raw header → canonical name
    missing_columns: list[str]
    unknown_columns: list[str]
    is_valid: bool


@dataclass
class SPValidationReport:
    total_rows: int
    valid_rows: int
    warning_rows: int
    error_rows: int
    quarantined_rows: int
    missing_columns: list[str]
    unknown_columns: list[str]
    date_range_start: date | None
    date_range_end: date | None
    currency: str | None
    marketplace: str | None
    report_type: str = "sponsored_products_search_term_report"
    schema_valid: bool = False
    can_generate_recommendations: bool = False
    top_issues: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "warning_rows": self.warning_rows,
            "error_rows": self.error_rows,
            "quarantined_rows": self.quarantined_rows,
            "missing_columns": self.missing_columns,
            "unknown_columns": self.unknown_columns,
            "date_range_start": self.date_range_start.isoformat() if self.date_range_start else None,
            "date_range_end": self.date_range_end.isoformat() if self.date_range_end else None,
            "currency": self.currency,
            "marketplace": self.marketplace,
            "report_type": self.report_type,
            "schema_valid": self.schema_valid,
            "can_generate_recommendations": self.can_generate_recommendations,
            "top_issues": self.top_issues,
        }


# ---------------------------------------------------------------------------
# Main pipeline class
# ---------------------------------------------------------------------------

class SPSearchTermPipeline:
    """Production-grade SP Search Term report processing pipeline.

    Usage::

        pipeline = SPSearchTermPipeline()
        validated, aggregated, report = pipeline.run(
            raw_rows=parsed_result.rows,   # list of row_data_json dicts
            original_headers=headers,       # list of raw header strings from UploadParser
        )
    """

    def run(
        self,
        *,
        raw_rows: list[dict],
        original_headers: list[str],
    ) -> tuple[list[SPValidatedRow], list[SPAggregatedRow], SPValidationReport]:
        schema = self.detect_schema(original_headers)
        seen_keys: dict[str, int] = {}
        validated_rows: list[SPValidatedRow] = []

        for idx, raw_row in enumerate(raw_rows):
            normalized = self._normalize_row(raw_row, schema.mapped_headers, row_number=idx + 2)
            validated = self._validate_row(normalized, seen_keys)
            validated_rows.append(validated)

        non_quarantined = [vr for vr in validated_rows if not vr.is_quarantined]
        aggregated = self._aggregate_rows(non_quarantined)
        report = self._build_report(validated_rows=validated_rows, schema=schema)
        return validated_rows, aggregated, report

    # ------------------------------------------------------------------
    # Schema detection
    # ------------------------------------------------------------------

    def detect_schema(self, headers: list[str]) -> SPSchemaResult:
        """Map raw headers → canonical names; identify missing required and unknown columns."""
        mapped: dict[str, str] = {}
        canonical_found: set[str] = set()
        unknown: list[str] = []

        for header in headers:
            key = _norm_key(header)
            canonical = SP_COLUMN_MAP.get(key)
            if canonical:
                if canonical not in canonical_found:  # first occurrence wins
                    mapped[header] = canonical
                    canonical_found.add(canonical)
            else:
                unknown.append(header)

        missing = sorted(REQUIRED_CANONICAL - canonical_found)
        return SPSchemaResult(
            mapped_headers=mapped,
            missing_columns=missing,
            unknown_columns=unknown,
            is_valid=not missing,
        )

    # ------------------------------------------------------------------
    # Row normalization
    # ------------------------------------------------------------------

    def _normalize_row(
        self, raw_row: dict, mapped_headers: dict[str, str], row_number: int
    ) -> SPNormalizedRow:
        canon: dict[str, Any] = {}
        for raw_key, value in raw_row.items():
            canonical_name = mapped_headers.get(raw_key)
            if canonical_name and canonical_name not in canon:
                canon[canonical_name] = value

        n = SPNormalizedRow(row_number=row_number, raw_data=raw_row)
        n.campaign_name = _to_str(canon.get("campaign_name"))
        n.ad_group_name = _to_str(canon.get("ad_group_name"))
        n.targeting = _to_str(canon.get("targeting"))
        n.match_type = _to_str(canon.get("match_type"))
        n.customer_search_term = _to_str(canon.get("customer_search_term"))
        n.portfolio_name = _to_str(canon.get("portfolio_name"))
        n.currency = _to_str(canon.get("currency"))
        n.retailer = _to_str(canon.get("retailer"))
        n.country = _to_str(canon.get("country"))
        n.start_date = _to_date(canon.get("start_date"))
        n.end_date = _to_date(canon.get("end_date"))
        n.impressions = _to_int(canon.get("impressions"))
        n.clicks = _to_int(canon.get("clicks"))
        n.total_orders = _to_int(canon.get("total_orders"))
        n.total_units = _to_int(canon.get("total_units"))
        n.advertised_sku_units = _to_int(canon.get("advertised_sku_units"))
        n.other_sku_units = _to_int(canon.get("other_sku_units"))
        n.spend = _to_decimal_currency(canon.get("spend"))
        n.total_sales = _to_decimal_currency(canon.get("total_sales"))
        n.advertised_sku_sales = _to_decimal_currency(canon.get("advertised_sku_sales"))
        n.other_sku_sales = _to_decimal_currency(canon.get("other_sku_sales"))
        # CPC is currency-formatted in CSV ("$0.82") but plain float in XLSX
        n.cpc = _to_decimal_currency(canon.get("cpc"))
        # Percentage fields: CSV → "14.17%", XLSX → 0.1417
        n.ctr = _to_decimal_percent(canon.get("ctr"))
        n.acos = _to_decimal_percent(canon.get("acos"))
        n.conversion_rate = _to_decimal_percent(canon.get("conversion_rate"))
        # ROAS is a plain ratio (not a percentage)
        n.roas = _to_decimal(canon.get("roas"))
        # Classification
        n.search_term_type = _classify_search_term(n.customer_search_term)
        n.targeting_type = _classify_targeting(n.targeting, n.match_type)
        return n

    # ------------------------------------------------------------------
    # Row validation
    # ------------------------------------------------------------------

    def _validate_row(
        self, normalized: SPNormalizedRow, seen_keys: dict[str, int]
    ) -> SPValidatedRow:
        n = normalized
        issues: list[RowIssue] = []

        # Quarantine summary/footer rows immediately
        if _is_summary_row(n):
            return SPValidatedRow(normalized=n, issues=[], is_quarantined=True)

        # Quarantine rows missing required identity fields
        for fname in REQUIRED_IDENTITY:
            if not getattr(n, fname):
                issues.append(RowIssue(
                    field=fname,
                    code="REQUIRED_FIELD_MISSING",
                    message=f"Required field '{fname}' is missing or empty.",
                    severity=RowSeverity.ERROR,
                ))
        if issues:
            return SPValidatedRow(normalized=n, issues=issues, is_quarantined=True)

        # Duplicate detection (warn, don't quarantine)
        dedup_key = (
            f"{n.campaign_name}|{n.ad_group_name}|{n.targeting}|"
            f"{n.match_type}|{n.customer_search_term}|{n.start_date}|{n.end_date}"
        )
        if dedup_key in seen_keys:
            issues.append(RowIssue(
                field="row",
                code="DUPLICATE_ROW",
                message=f"Duplicate row; same key as row {seen_keys[dedup_key]}.",
                severity=RowSeverity.WARNING,
            ))
        else:
            seen_keys[dedup_key] = n.row_number

        # Non-negative checks
        for fname, val in [
            ("impressions", n.impressions),
            ("clicks", n.clicks),
            ("spend", n.spend),
            ("total_sales", n.total_sales),
            ("total_orders", n.total_orders),
            ("total_units", n.total_units),
        ]:
            if val is not None and val < 0:
                issues.append(RowIssue(
                    field=fname,
                    code="NEGATIVE_VALUE",
                    message=f"'{fname}' must not be negative (got {val}).",
                    severity=RowSeverity.ERROR,
                ))

        # Date order
        if n.start_date and n.end_date and n.end_date < n.start_date:
            issues.append(RowIssue(
                field="end_date",
                code="DATE_ORDER_INVALID",
                message=f"end_date ({n.end_date}) is before start_date ({n.start_date}).",
                severity=RowSeverity.ERROR,
            ))

        imp = n.impressions or 0
        clk = n.clicks or 0
        spd = n.spend or Decimal(0)
        sal = n.total_sales or Decimal(0)
        ord_ = n.total_orders or 0

        # clicks ≤ impressions (warning only — Amazon can report reporting lags)
        if imp > 0 and clk > imp:
            issues.append(RowIssue(
                field="clicks",
                code="CLICKS_EXCEED_IMPRESSIONS",
                message=f"clicks ({clk}) exceeds impressions ({imp}).",
                severity=RowSeverity.WARNING,
            ))

        # CTR ≈ clicks / impressions
        if imp > 0 and n.ctr is not None:
            expected = Decimal(clk) / Decimal(imp)
            if not _within_tolerance(n.ctr, expected):
                issues.append(RowIssue(
                    field="ctr",
                    code="CTR_MISMATCH",
                    message=f"CTR {n.ctr:.4f} ≠ clicks/impressions {expected:.4f} (>10% off).",
                    severity=RowSeverity.WARNING,
                ))

        # CPC ≈ spend / clicks  (skip when clicks = 0 — blank CPC is expected)
        if clk > 0 and n.cpc is not None:
            expected = spd / Decimal(clk)
            if not _within_tolerance(n.cpc, expected):
                issues.append(RowIssue(
                    field="cpc",
                    code="CPC_MISMATCH",
                    message=f"CPC {n.cpc:.4f} ≠ spend/clicks {expected:.4f} (>10% off).",
                    severity=RowSeverity.WARNING,
                ))

        # CPC present with zero clicks is suspicious
        if clk == 0 and n.cpc is not None and n.cpc > 0:
            issues.append(RowIssue(
                field="cpc",
                code="CPC_WITH_ZERO_CLICKS",
                message="CPC is non-zero but clicks is zero.",
                severity=RowSeverity.WARNING,
            ))

        # ACOS ≈ spend / total_sales  (skip when sales = 0 — blank ACOS is expected)
        if sal > 0 and n.acos is not None:
            expected = spd / sal
            if not _within_tolerance(n.acos, expected):
                issues.append(RowIssue(
                    field="acos",
                    code="ACOS_MISMATCH",
                    message=f"ACOS {n.acos:.4f} ≠ spend/sales {expected:.4f} (>10% off).",
                    severity=RowSeverity.WARNING,
                ))

        # ROAS ≈ total_sales / spend  (skip when spend = 0)
        if spd > 0 and n.roas is not None:
            expected = sal / spd
            if not _within_tolerance(n.roas, expected):
                issues.append(RowIssue(
                    field="roas",
                    code="ROAS_MISMATCH",
                    message=f"ROAS {n.roas:.4f} ≠ sales/spend {expected:.4f} (>10% off).",
                    severity=RowSeverity.WARNING,
                ))

        # CVR ≈ orders / clicks  (skip when clicks = 0)
        if clk > 0 and n.conversion_rate is not None:
            expected = Decimal(ord_) / Decimal(clk)
            if not _within_tolerance(n.conversion_rate, expected):
                issues.append(RowIssue(
                    field="conversion_rate",
                    code="CVR_MISMATCH",
                    message=f"CVR {n.conversion_rate:.4f} ≠ orders/clicks {expected:.4f} (>10% off).",
                    severity=RowSeverity.WARNING,
                ))

        # advertised_sku_sales + other_sku_sales ≈ total_sales
        if n.advertised_sku_sales is not None and n.other_sku_sales is not None and n.total_sales is not None:
            sku_total = n.advertised_sku_sales + n.other_sku_sales
            if not _within_tolerance(n.total_sales, sku_total):
                issues.append(RowIssue(
                    field="total_sales",
                    code="SKU_SALES_SUM_MISMATCH",
                    message=(
                        f"advertised_sku_sales + other_sku_sales = {sku_total:.4f} "
                        f"≠ total_sales {n.total_sales:.4f} (>10% off)."
                    ),
                    severity=RowSeverity.WARNING,
                ))

        # advertised_sku_units + other_sku_units ≈ total_units
        if (
            n.advertised_sku_units is not None
            and n.other_sku_units is not None
            and n.total_units is not None
        ):
            sku_units = n.advertised_sku_units + n.other_sku_units
            diff = abs(sku_units - n.total_units)
            threshold = max(1, int(n.total_units * 0.10))
            if diff > threshold:
                issues.append(RowIssue(
                    field="total_units",
                    code="SKU_UNITS_SUM_MISMATCH",
                    message=(
                        f"advertised_sku_units + other_sku_units = {sku_units} "
                        f"≠ total_units {n.total_units} (>{threshold} units off)."
                    ),
                    severity=RowSeverity.WARNING,
                ))

        return SPValidatedRow(normalized=n, issues=issues)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate_rows(self, validated_rows: list[SPValidatedRow]) -> list[SPAggregatedRow]:
        groups: dict[tuple, SPAggregatedRow] = {}

        for vr in validated_rows:
            n = vr.normalized
            key = (
                n.campaign_name or "",
                n.ad_group_name or "",
                n.targeting or "",
                n.customer_search_term or "",
                n.match_type or "",
            )
            if key not in groups:
                groups[key] = SPAggregatedRow(
                    campaign_name=key[0],
                    ad_group_name=key[1],
                    targeting=key[2],
                    customer_search_term=key[3],
                    match_type=key[4],
                    search_term_type=n.search_term_type,
                    targeting_type=n.targeting_type,
                    currency=n.currency,
                )
            agg = groups[key]
            agg.row_count += 1
            agg.total_impressions += n.impressions or 0
            agg.total_clicks += n.clicks or 0
            agg.total_spend += n.spend or Decimal(0)
            agg.total_sales += n.total_sales or Decimal(0)
            agg.total_orders += n.total_orders or 0
            agg.total_units += n.total_units or 0
            if n.start_date:
                agg.start_date = min(agg.start_date, n.start_date) if agg.start_date else n.start_date
            if n.end_date:
                agg.end_date = max(agg.end_date, n.end_date) if agg.end_date else n.end_date

        for agg in groups.values():
            imp = Decimal(agg.total_impressions)
            clk = Decimal(agg.total_clicks)
            agg.agg_ctr = _safe_div(clk, imp)
            agg.agg_cpc = _safe_div(agg.total_spend, clk)
            agg.agg_acos = _safe_div(agg.total_spend, agg.total_sales)
            agg.agg_roas = _safe_div(agg.total_sales, agg.total_spend)
            agg.agg_cvr = _safe_div(Decimal(agg.total_orders), clk)

        return list(groups.values())

    # ------------------------------------------------------------------
    # Validation report
    # ------------------------------------------------------------------

    def _build_report(
        self,
        *,
        validated_rows: list[SPValidatedRow],
        schema: SPSchemaResult,
    ) -> SPValidationReport:
        valid = sum(1 for vr in validated_rows if vr.effective_severity == RowSeverity.OK)
        warnings = sum(1 for vr in validated_rows if vr.effective_severity == RowSeverity.WARNING)
        errors = sum(1 for vr in validated_rows if vr.effective_severity == RowSeverity.ERROR)
        quarantined = sum(1 for vr in validated_rows if vr.is_quarantined)

        non_q = [vr for vr in validated_rows if not vr.is_quarantined]
        start_dates = [vr.normalized.start_date for vr in non_q if vr.normalized.start_date]
        end_dates = [vr.normalized.end_date for vr in non_q if vr.normalized.end_date]
        date_range_start = min(start_dates) if start_dates else None
        date_range_end = max(end_dates) if end_dates else None

        currencies = {vr.normalized.currency for vr in non_q if vr.normalized.currency}
        currency = next(iter(currencies)) if len(currencies) == 1 else None

        # Report mixed currencies as a top-level issue
        extra_top: list[dict] = []
        if len(currencies) > 1:
            extra_top.append({
                "code": "MIXED_CURRENCIES",
                "count": len(validated_rows),
                "severity": "error",
                "detail": f"Multiple currencies found: {sorted(currencies)}",
            })

        countries = {vr.normalized.country for vr in non_q if vr.normalized.country}
        marketplace = next(iter(countries)) if len(countries) == 1 else None

        # Issue frequency table
        code_counts: dict[str, int] = {}
        for vr in validated_rows:
            for issue in vr.issues:
                code_counts[issue.code] = code_counts.get(issue.code, 0) + 1
        top_issues = extra_top + sorted(
            [
                {"code": code, "count": cnt, "severity": _severity_for_code(code)}
                for code, cnt in code_counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        schema_valid = schema.is_valid
        # Block recommendations only on schema errors; row-level warnings are OK.
        can_recommend = schema_valid and quarantined < max(1, len(validated_rows))

        return SPValidationReport(
            total_rows=len(validated_rows),
            valid_rows=valid,
            warning_rows=warnings,
            error_rows=errors,
            quarantined_rows=quarantined,
            missing_columns=schema.missing_columns,
            unknown_columns=schema.unknown_columns,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            currency=currency,
            marketplace=marketplace,
            schema_valid=schema_valid,
            can_generate_recommendations=can_recommend,
            top_issues=top_issues,
        )


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _classify_search_term(term: str | None) -> str | None:
    if not term:
        return None
    t = term.strip()
    if _ASIN_RE.match(t) or _NUMERIC_ASIN_RE.match(t):
        return "asin"
    return "keyword"


def _classify_targeting(targeting: str | None, match_type: str | None) -> str | None:
    if not targeting:
        return None
    t = targeting.strip()
    t_lower = t.lower()
    if t_lower in _AUTO_TARGETING_VALUES:
        return "auto"
    # Amazon keyword-group= is an auto-targeting group (real data: keyword-group="Keywords related to...")
    if t_lower.startswith("keyword-group="):
        return "auto"
    # ASIN targeting: asin=, asin:, asin-expanded= (expanded ASIN), or bare ASIN token
    if (
        t_lower.startswith("asin=")
        or t_lower.startswith("asin:")
        or t_lower.startswith("asin-expanded=")
        or _ASIN_RE.match(t)
    ):
        return "product_asin"
    # Category targeting — standalone ("category=...") or compound ("price>10.0 category=...")
    if "category=" in t_lower or "category:" in t_lower:
        return "category"
    # Match type signals manual keyword
    if match_type and match_type.lower() in ("exact", "phrase", "broad"):
        return "keyword"
    return "keyword"


# ---------------------------------------------------------------------------
# Value coercion helpers
# ---------------------------------------------------------------------------

def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return int(round(float(s)))
    except (ValueError, TypeError):
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _to_decimal_currency(value: Any) -> Decimal | None:
    """Handle '$104.14', '€99.50', or plain 104.14 (from XLSX)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    s = str(value).strip()
    if not s:
        return None
    s = _CURRENCY_PREFIX_RE.sub("", s).replace(",", "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _to_decimal_percent(value: Any) -> Decimal | None:
    """
    Parse percentage values.

    - CSV source: "14.17%" → strips %, divides by 100 → Decimal("0.1417")
    - XLSX source: 0.1417 (float already as fraction) → Decimal("0.1417")
    - XLSX source: 0 (zero sales rows) → Decimal("0")
    - Empty / None → None
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        # XLSX stores percentages as fractions
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("%"):
        try:
            return Decimal(s[:-1].strip()) / Decimal(100)
        except InvalidOperation:
            return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _within_tolerance(actual: Decimal, expected: Decimal) -> bool:
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / abs(expected) <= RATIO_TOLERANCE


def _safe_div(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _is_summary_row(n: SPNormalizedRow) -> bool:
    """Return True for total/summary rows that should be quarantined."""
    if n.campaign_name:
        lower = n.campaign_name.lower().strip()
        if lower in _SUMMARY_PATTERNS or lower.startswith("total "):
            return True
    return False


def _severity_for_code(code: str) -> str:
    _errors = {"REQUIRED_FIELD_MISSING", "NEGATIVE_VALUE", "DATE_ORDER_INVALID"}
    return "error" if code in _errors else "warning"
