import re
from collections.abc import Iterable

from apps.api.app.schemas.account_imports import DetectionConfidence, EntityType, ReportDetectionResult, ReportType


SEARCH_TERM_REQUIRED = {
    "customer search term",
    "targeting",
    "campaign name",
    "ad group name",
    "spend",
    "sales",
    "orders",
}

TARGETING_REQUIRED = {
    "targeting",
    "campaign name",
    "ad group name",
    "spend",
    "sales",
    "orders",
}

CAMPAIGN_REQUIRED = {
    "campaign name",
    "campaign id",
    "spend",
    "sales",
    "orders",
}

BULK_SHEET_REQUIRED = {
    "product",
    "entity",
    "operation",
    "campaign id",
    "ad group id",
    "portfolio id",
    "sku",
    "asin",
    "bid",
    "budget",
}

PRODUCT_IDENTIFIER_ALIASES = {
    "asin": {"asin", "advertised asin", "purchased asin", "advertised product asin"},
    "sku": {"sku", "advertised sku", "seller sku", "merchant sku"},
    "product_name": {"product", "product name", "advertised product", "portfolio name"},
}

ENTITY_COLUMNS = {
    EntityType.PRODUCT: {"asin", "sku", "product", "product name", "advertised product", "advertised asin", "advertised sku"},
    EntityType.CAMPAIGN: {"campaign", "campaign name", "campaign id"},
    EntityType.AD_GROUP: {"ad group", "ad group name", "ad group id"},
    EntityType.TARGET: {"targeting", "keyword", "keyword text", "targeting expression", "targeting id"},
    EntityType.SEARCH_TERM: {"customer search term", "search term", "query"},
}


class ReportTypeDetector:
    def detect(self, *, headers: Iterable[str], sample_rows: Iterable[dict] | None = None) -> ReportDetectionResult:
        normalized_headers = {_normalize_header(header) for header in headers if str(header).strip()}
        normalized_headers = _expand_known_aliases(normalized_headers)
        sample_report_type = _detect_from_sample_rows(sample_rows or [])

        if _has_required(normalized_headers, BULK_SHEET_REQUIRED):
            report_type = ReportType.BULK_SHEET
            required = BULK_SHEET_REQUIRED
            confidence = DetectionConfidence.HIGH
        elif _has_required(normalized_headers, SEARCH_TERM_REQUIRED):
            report_type = ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT
            required = SEARCH_TERM_REQUIRED
            confidence = DetectionConfidence.HIGH
        elif _has_required(normalized_headers, TARGETING_REQUIRED):
            report_type = ReportType.SPONSORED_PRODUCTS_TARGETING_REPORT
            required = TARGETING_REQUIRED
            confidence = DetectionConfidence.MEDIUM
        elif _has_required(normalized_headers, CAMPAIGN_REQUIRED):
            report_type = ReportType.SPONSORED_PRODUCTS_CAMPAIGN_REPORT
            required = CAMPAIGN_REQUIRED
            confidence = DetectionConfidence.MEDIUM
        elif sample_report_type is not None:
            report_type = sample_report_type
            required = _required_for(report_type)
            confidence = DetectionConfidence.LOW
        else:
            report_type = ReportType.UNKNOWN_REPORT
            required = set()
            confidence = DetectionConfidence.LOW

        missing = sorted(required - normalized_headers) if required else []
        available_entity_levels = _available_entity_levels(normalized_headers)
        product_identifiers = _product_identifiers(normalized_headers)
        return ReportDetectionResult(
            detected_report_type=report_type,
            confidence=confidence,
            required_columns_present=not missing and report_type != ReportType.UNKNOWN_REPORT,
            missing_columns=missing,
            available_entity_levels=available_entity_levels,
            product_identifiers_available=product_identifiers,
        )


def detect_report_type(*, rows: list[dict]) -> ReportDetectionResult:
    headers = rows[0].keys() if rows else []
    return ReportTypeDetector().detect(headers=headers, sample_rows=rows[:25])


def _available_entity_levels(headers: set[str]) -> list[EntityType]:
    levels = [EntityType.ACCOUNT]
    for level, aliases in ENTITY_COLUMNS.items():
        if headers & aliases:
            levels.append(level)
    return levels


def _product_identifiers(headers: set[str]) -> list[str]:
    identifiers = []
    for identifier, aliases in PRODUCT_IDENTIFIER_ALIASES.items():
        if headers & aliases:
            identifiers.append(identifier)
    return identifiers


def _detect_from_sample_rows(rows: Iterable[dict]) -> ReportType | None:
    for row in rows:
        entity_value = _value_for(row, "entity")
        if entity_value and entity_value.lower() in {"campaign", "ad group", "keyword", "product ad", "bidding adjustment"}:
            return ReportType.BULK_SHEET
        search_term = _value_for(row, "customer search term") or _value_for(row, "search term")
        targeting = _value_for(row, "targeting") or _value_for(row, "keyword")
        if search_term and targeting:
            return ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT
    return None


def _value_for(row: dict, desired_header: str) -> str | None:
    desired = _normalize_header(desired_header)
    for key, value in row.items():
        if _normalize_header(str(key)) == desired and value is not None:
            text = str(value).strip()
            return text or None
    return None


def _required_for(report_type: ReportType) -> set[str]:
    return {
        ReportType.BULK_SHEET: BULK_SHEET_REQUIRED,
        ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT: SEARCH_TERM_REQUIRED,
        ReportType.SPONSORED_PRODUCTS_TARGETING_REPORT: TARGETING_REQUIRED,
        ReportType.SPONSORED_PRODUCTS_CAMPAIGN_REPORT: CAMPAIGN_REQUIRED,
    }.get(report_type, set())


def _has_required(headers: set[str], required: set[str]) -> bool:
    return required.issubset(headers)


def _expand_known_aliases(headers: set[str]) -> set[str]:
    expanded = set(headers)

    _strip_info_suffixes(expanded)

    if "7 day total sales" in expanded:
        expanded.add("sales")
    if "14 day total sales" in expanded:
        expanded.add("sales")
    if "7 day total orders" in expanded:
        expanded.add("orders")
    if "14 day total orders" in expanded:
        expanded.add("orders")
    if "campaign" in expanded:
        expanded.add("campaign name")
    if "ad group" in expanded:
        expanded.add("ad group name")

    if "daily budget" in expanded:
        expanded.add("budget")
    if "campaign daily budget" in expanded:
        expanded.add("budget")
    if "ad group default bid" in expanded:
        expanded.add("bid")
    if "asin" in expanded or "advertised asin" in expanded:
        expanded.add("asin")
    if "sku" in expanded or "advertised sku" in expanded:
        expanded.add("sku")
    return expanded


def _strip_info_suffixes(headers: set[str]) -> None:
    """Remove 'informational only' suffixes and add stripped versions.

    Amazon bulk workbooks often have columns like:
    'Campaign Name (Informational only)' alongside 'Campaign Name'.
    After normalization, these become 'campaign name informational only'.
    This ensures both forms map to the same canonical names.
    """
    info_suffix = " informational only"
    additions: set[str] = set()
    for header in headers:
        if header.endswith(info_suffix):
            stripped = header[:-len(info_suffix)]
            additions.add(stripped)
    headers.update(additions)


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()
