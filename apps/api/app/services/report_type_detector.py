import json
import re
from collections.abc import Iterable

from apps.api.app.schemas.account_imports import DetectionConfidence, EntityType, ReportDetectionResult, ReportType
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet


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
    if "total sales" in expanded:
        expanded.add("sales")
    if "7 day total orders" in expanded:
        expanded.add("orders")
    if "14 day total orders" in expanded:
        expanded.add("orders")
    if "7 day total orders number" in expanded:
        expanded.add("orders")
    if "14 day total orders number" in expanded:
        expanded.add("orders")
    if "total orders" in expanded:
        expanded.add("orders")
    if "cost" in expanded:
        expanded.add("spend")
    if "customer search term" in expanded:
        expanded.add("search term")
    if "search term" in expanded:
        expanded.add("customer search term")
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


# =============================================================================
# Dual-Path Report Type Detection: Deterministic + AI
# =============================================================================

REPORT_DETECTION_AI_AGENT_ID = "report_detection_agent"


class DualPathReportTypeDetection(DualPathDecisionService[dict]):
    """Dual-path report type detection service.

    Deterministic path: detect() (exact header-matching rules).
    AI path: LLM analyzes headers and sample rows to detect report type.
    Both paths produce the same output schema (detection result dict).
    """

    AGENT_ID = REPORT_DETECTION_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Report Detection Agent"

    def _deterministic_path(self, inputs: dict) -> dict:
        """Run deterministic report type detection."""
        headers: list[str] = inputs["headers"]
        sample_rows: list[dict] = inputs.get("sample_rows", [])
        result = ReportTypeDetector().detect(headers=headers, sample_rows=sample_rows)
        return {
            "detected_report_type": result.detected_report_type.value,
            "confidence": result.confidence.value,
            "required_columns_present": result.required_columns_present,
            "missing_columns": result.missing_columns,
            "available_entity_levels": [level.value for level in result.available_entity_levels],
            "product_identifiers_available": result.product_identifiers_available,
            "decision_source": "deterministic",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        headers: list[str] = inputs["headers"]
        sample_rows: list[dict] = inputs.get("sample_rows", [])
        sample_rows_for_prompt = sample_rows[:5] if sample_rows else []

        system = (
            "You are the AdSurf Report Detection Agent for Amazon Ads reports. "
            "Your job is to detect the type of an uploaded Amazon Ads report from its headers and sample data. "
            f"{safety_prompt_snippet()}"
            "You detect report types only — you do not modify or approve anything. "
            "Return JSON only. "
            "Every output must include decision_source='ai' and requires_human_approval=true."
        )
        user = {
            "task": "detect_report_type",
            "headers": headers,
            "sample_rows": sample_rows_for_prompt,
            "known_report_types": {
                "bulk_sheet": {"required_columns": sorted(BULK_SHEET_REQUIRED)},
                "sponsored_products_search_term_report": {"required_columns": sorted(SEARCH_TERM_REQUIRED)},
                "sponsored_products_targeting_report": {"required_columns": sorted(TARGETING_REQUIRED)},
                "sponsored_products_campaign_report": {"required_columns": sorted(CAMPAIGN_REQUIRED)},
                "unknown_report": {"description": "Does not match any known report type"},
            },
            "required_output_shape": {
                "detected_report_type": "bulk_sheet | sponsored_products_search_term_report | sponsored_products_targeting_report | sponsored_products_campaign_report | unknown_report",
                "confidence": "high | medium | low",
                "required_columns_present": "boolean",
                "missing_columns": ["list of missing required column names"],
                "available_entity_levels": ["account | product | campaign | ad_group | target | search_term"],
                "product_identifiers_available": ["asin | sku | product_name"],
                "reasoning": "brief explanation",
                "decision_source": "ai",
                "requires_human_approval": True,
                "executes_live_amazon_change": False,
            },
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)},
        ]

    def _validate_ai_output(self, ai_json: dict, inputs: dict) -> list[str]:
        errors: list[str] = []
        valid_types = {"bulk_sheet", "sponsored_products_search_term_report", "sponsored_products_targeting_report", "sponsored_products_campaign_report", "unknown_report"}
        if ai_json.get("detected_report_type") not in valid_types:
            errors.append(f"detected_report_type must be one of: {sorted(valid_types)}.")
        if ai_json.get("decision_source") != "ai":
            errors.append("decision_source must be 'ai'.")
        if ai_json.get("requires_human_approval") is not True:
            errors.append("requires_human_approval must be true.")
        if ai_json.get("executes_live_amazon_change") is not False:
            errors.append("executes_live_amazon_change must be false.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> dict:
        return {
            "detected_report_type": ai_json.get("detected_report_type", "unknown_report"),
            "confidence": ai_json.get("confidence", "low"),
            "required_columns_present": ai_json.get("required_columns_present", False),
            "missing_columns": ai_json.get("missing_columns", []),
            "available_entity_levels": ai_json.get("available_entity_levels", []),
            "product_identifiers_available": ai_json.get("product_identifiers_available", []),
            "reasoning": ai_json.get("reasoning", ""),
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _empty_result(self) -> dict:
        return {
            "detected_report_type": "unknown_report",
            "confidence": "low",
            "required_columns_present": False,
            "missing_columns": [],
            "available_entity_levels": [],
            "product_identifiers_available": [],
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }
