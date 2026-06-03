import json
import re
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.column_mapping import ColumnMappingRepository
from apps.api.app.schemas.column_mapping import (
    ColumnInferredDataType,
    ColumnMapping,
    ColumnMappingStatus,
    ColumnProfile,
    ColumnProfileColumn,
    ManualMappingJson,
)
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet


MAX_COMPETITOR_RANK_COLUMNS = 10

# Column name tokens that indicate ad performance metrics — these columns
# should NEVER be accepted as competitor rank columns even when numeric,
# because their values are not rank positions and would produce meaningless
# relevance scores (scorer counts rank values < 15).
_FORBIDDEN_RANK_COLUMN_PATTERNS: list[str] = [
    # Spend / cost
    "spend", "cost", "cpc", "ecpc", "cpm", "ecpm",
    # Clicks / traffic
    "click", "clicks", "ctr",
    # Orders / conversions
    "order", "orders", "cvr", "conversion", "conversions",
    # Sales / revenue
    "sale", "sales", "revenue", "acos", "roas", "tacos", "tros",
    # Impressions
    "impression", "impressions",
    # Budget / bid
    "budget", "bid", "bids",
    # Other ad metrics
    "acos", "roas",
]

# Value-level heuristics that indicate a column contains ad metric data
# rather than organic rank positions.
_RANK_VALUE_MAX_REASONABLE = 1000  # ranks above this are likely not ranks
_RANK_VALUE_DECIMAL_FRACTION_WARN = 0.3  # warn if >30% of values have decimal parts
_RANK_VALUE_LOW_PCT_WARN = 0.1  # warn if <10% of values are in rank range (1-100)


class ColumnMappingService:
    def __init__(self, *, column_repository: ColumnMappingRepository) -> None:
        self._column_repository = column_repository

    def create_manual_mapping(
        self,
        *,
        workspace_id: UUID,
        upload_id: UUID,
        column_profile_id: UUID,
        mapping_json: ManualMappingJson,
        created_by: str,
    ) -> ColumnMapping:
        profile_with_columns = self._column_repository.get_profile(
            workspace_id=workspace_id,
            upload_id=upload_id,
            column_profile_id=column_profile_id,
        )
        if profile_with_columns is None:
            raise ApiError(code="COLUMN_PROFILE_NOT_FOUND", message="Column profile was not found.", status_code=404)
        profile, columns = profile_with_columns
        status, messages, canonical_mapping = validate_manual_mapping(profile=profile, columns=columns, mapping_json=mapping_json)
        return self._column_repository.create_mapping(
            profile=profile,
            mapping_json=canonical_mapping,
            validation_messages=messages,
            status=status,
            created_by=created_by,
        )


def validate_manual_mapping(
    *,
    profile: ColumnProfile,
    columns: list[ColumnProfileColumn],
    mapping_json: ManualMappingJson,
) -> tuple[ColumnMappingStatus, list[dict], dict]:
    messages: list[dict] = []
    resolved: dict[str, ColumnProfileColumn | list[ColumnProfileColumn] | None] = {
        "search_term": None,
        "search_volume": None,
        "competitor_rank_columns": [],
    }

    search_term = _resolve_column(mapping_json.search_term, columns)
    search_volume = _resolve_column(mapping_json.search_volume, columns)
    competitor_rank_columns = [_resolve_column(reference, columns) for reference in mapping_json.competitor_rank_columns]

    if mapping_json.search_term is None:
        _message(messages, "error", "MISSING_SEARCH_TERM", "search_term is required.")
    elif search_term is None:
        _message(messages, "error", "UNKNOWN_SEARCH_TERM_COLUMN", "search_term references a column that does not exist.")
    else:
        resolved["search_term"] = search_term

    if mapping_json.search_volume is None:
        _message(messages, "error", "MISSING_SEARCH_VOLUME", "search_volume is required.")
    elif search_volume is None:
        _message(messages, "error", "UNKNOWN_SEARCH_VOLUME_COLUMN", "search_volume references a column that does not exist.")
    else:
        resolved["search_volume"] = search_volume

    if not mapping_json.competitor_rank_columns:
        _message(messages, "error", "MISSING_COMPETITOR_RANK_COLUMNS", "At least one competitor rank column is required.")
    if len(mapping_json.competitor_rank_columns) > MAX_COMPETITOR_RANK_COLUMNS:
        _message(messages, "error", "TOO_MANY_COMPETITOR_RANK_COLUMNS", "Competitor rank columns must contain 1 to 10 columns.")
    if any(column is None for column in competitor_rank_columns):
        _message(messages, "error", "UNKNOWN_COMPETITOR_RANK_COLUMN", "A competitor rank column reference does not exist.")
    valid_rank_columns = [column for column in competitor_rank_columns if column is not None]
    resolved["competitor_rank_columns"] = valid_rank_columns

    role_column_ids = {
        "search_term": search_term.id if search_term else None,
        "search_volume": search_volume.id if search_volume else None,
    }
    if role_column_ids["search_term"] and role_column_ids["search_term"] == role_column_ids["search_volume"]:
        _message(messages, "error", "DUPLICATE_SEARCH_TERM_SEARCH_VOLUME", "search_term and search_volume must use different columns.")

    rank_ids = [column.id for column in valid_rank_columns]
    if len(rank_ids) != len(set(rank_ids)):
        _message(messages, "error", "DUPLICATE_COMPETITOR_RANK_COLUMNS", "competitor_rank_columns must be unique.")
    for column in valid_rank_columns:
        if column.id in {role_column_ids["search_term"], role_column_ids["search_volume"]}:
            _message(messages, "error", "DUPLICATE_COMPETITOR_RANK_ROLE", "competitor_rank_columns cannot include search_term or search_volume columns.")

    if search_volume is not None:
        _validate_numeric_like(messages, search_volume, "search_volume", "SEARCH_VOLUME_NOT_NUMERIC")
    for column in valid_rank_columns:
        _validate_numeric_like(messages, column, "competitor_rank_columns", "COMPETITOR_RANK_NOT_NUMERIC")
        _validate_competitor_rank_semantics(messages, column)
    if search_term is not None:
        _validate_search_term(messages, search_term)

    canonical_mapping = {
        "search_term": _column_reference(search_term),
        "search_volume": _column_reference(search_volume),
        "competitor_rank_columns": [_column_reference(column) for column in valid_rank_columns],
    }
    status = ColumnMappingStatus.INVALID if any(message["severity"] == "error" for message in messages) else ColumnMappingStatus.VALID
    return status, messages, canonical_mapping


def _resolve_column(reference: str | None, columns: list[ColumnProfileColumn]) -> ColumnProfileColumn | None:
    if reference is None:
        return None
    normalized_reference = reference.strip()
    if not normalized_reference:
        return None
    for column in columns:
        if normalized_reference in {str(column.id), column.original_column_name, column.normalized_column_name}:
            return column
    return None


def _validate_numeric_like(messages: list[dict], column: ColumnProfileColumn, field: str, code: str) -> None:
    if column.inferred_data_type in {ColumnInferredDataType.INTEGER, ColumnInferredDataType.DECIMAL}:
        return
    samples = [value for value in column.sample_values_json if value is not None]
    if samples and all(_is_numeric_like(value) for value in samples):
        _message(messages, "warning", f"{code}_TEXT", f"{field} uses text values that look numeric.", column)
        return
    _message(messages, "error", code, f"{field} must reference a numeric-like column.", column)


def _validate_competitor_rank_semantics(messages: list[dict], column: ColumnProfileColumn) -> None:
    """Validate that a column is semantically appropriate for competitor rank scoring.

    This performs a multi-layered check beyond simple numeric-ness:
    1. Column name is checked against forbidden ad-metric patterns (spend, clicks,
       orders, etc.) — these produce error-level rejections.
    2. Sample values are inspected for rank-like distribution (values in 1-100
       range, low decimal fraction) — these produce warning-level guidance.
    3. If the column name contains rank/position/competitor tokens, it passes.
    """
    normalized = column.normalized_column_name.lower()
    original_lower = column.original_column_name.lower()
    tokens = re.split(r"[\W_]+", normalized)

    # --- Layer 1: Forbidden ad metric name patterns (hard error) ---
    for pattern in _FORBIDDEN_RANK_COLUMN_PATTERNS:
        if pattern in normalized or pattern in original_lower:
            _message(
                messages,
                "error",
                "COMPETITOR_RANK_IS_AD_METRIC",
                f"competitor_rank_columns cannot use ad performance metric '{column.original_column_name}'. "
                f"Values like '{pattern}' are not rank positions — they would produce meaningless relevance scores.",
                column,
            )
            return

    # --- Layer 2: Positive name signals (pass-through) ---
    rank_positive_tokens = ("rank", "position", "organic", "competitor")
    if any(token in normalized for token in rank_positive_tokens) or "comp" in tokens:
        return

    # --- Layer 3: Value-level heuristics (warning, not hard error) ---
    _check_rank_value_heuristics(messages, column)

    # --- Layer 4: No positive signals found — name-based rejection ---
    _message(
        messages,
        "error",
        "COMPETITOR_RANK_NAME_NOT_RANK_LIKE",
        "competitor_rank_columns must reference rank or position columns, not unrelated performance metrics. "
        f"Column '{column.original_column_name}' does not contain rank-related tokens "
        "(e.g., 'rank', 'position', 'organic', 'competitor').",
        column,
    )


def _check_rank_value_heuristics(messages: list[dict], column: ColumnProfileColumn) -> None:
    """Inspect sample values for rank-like characteristics and issue warnings if
    the data looks more like ad metrics than organic rank positions."""
    samples = [value for value in column.sample_values_json if value is not None]
    if not samples:
        return

    numeric_values: list[float] = []
    for value in samples:
        parsed = _try_parse_float(value)
        if parsed is not None:
            numeric_values.append(parsed)

    if not numeric_values:
        return

    total = len(numeric_values)
    # Values that look like plausible rank positions (1–100)
    rank_range_count = sum(1 for v in numeric_values if 1.0 <= v <= 100.0)
    # Values with fractional parts (ad metrics like CPC $1.23)
    decimal_count = sum(1 for v in numeric_values if v != int(v))
    # Values above a reasonable rank ceiling (e.g., 1000+ impressions)
    high_value_count = sum(1 for v in numeric_values if v > _RANK_VALUE_MAX_REASONABLE)

    rank_pct = rank_range_count / total
    decimal_pct = decimal_count / total
    high_pct = high_value_count / total

    if high_pct > 0.5:
        _message(
            messages,
            "warning",
            "COMPETITOR_RANK_HIGH_VALUES",
            f"competitor_rank column '{column.original_column_name}' has {high_pct:.0%} of sample values "
            f"above {_RANK_VALUE_MAX_REASONABLE}, which does not look like rank positions. "
            "Verify this column contains organic rank data, not ad metrics like impressions or spend.",
            column,
        )
    if decimal_pct > _RANK_VALUE_DECIMAL_FRACTION_WARN:
        _message(
            messages,
            "warning",
            "COMPETITOR_RANK_DECIMAL_VALUES",
            f"competitor_rank column '{column.original_column_name}' has {decimal_pct:.0%} of sample values "
            "with decimal parts. Rank positions are typically whole numbers; decimal values suggest "
            "ad metrics like CPC or CVR. Verify this column contains rank data.",
            column,
        )
    if rank_pct < _RANK_VALUE_LOW_PCT_WARN and rank_pct > 0:
        _message(
            messages,
            "warning",
            "COMPETITOR_RANK_LOW_RANK_RANGE",
            f"Only {rank_pct:.0%} of sample values in '{column.original_column_name}' fall in the 1–100 rank range. "
            "This column may not represent organic rank positions.",
            column,
        )


def _try_parse_float(value) -> float | None:
    """Attempt to parse a value as float; returns None on failure."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip().replace(",", "")
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _validate_search_term(messages: list[dict], column: ColumnProfileColumn) -> None:
    samples = [value for value in column.sample_values_json if value is not None]
    if not samples:
        return
    numeric_count = sum(1 for value in samples if _is_numeric_like(value))
    if numeric_count == len(samples):
        _message(messages, "error", "SEARCH_TERM_NUMERIC_ONLY", "search_term appears to contain only numeric values.", column)
    elif numeric_count > 0:
        _message(messages, "warning", "SEARCH_TERM_PARTLY_NUMERIC", "search_term contains some numeric-only samples.", column)


def _is_numeric_like(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip().replace(",", "")
    if not stripped:
        return False
    try:
        float(stripped)
        return True
    except ValueError:
        return False


def _column_reference(column: ColumnProfileColumn | None) -> dict | None:
    if column is None:
        return None
    return {
        "column_id": str(column.id),
        "original_column_name": column.original_column_name,
        "normalized_column_name": column.normalized_column_name,
    }


def _message(
    messages: list[dict],
    severity: str,
    code: str,
    message: str,
    column: ColumnProfileColumn | None = None,
) -> None:
    payload = {"severity": severity, "code": code, "message": message}
    if column is not None:
        payload["column_id"] = str(column.id)
        payload["column_name"] = column.original_column_name
    messages.append(payload)


# =============================================================================
# Dual-Path Column Mapping: Deterministic + AI
# =============================================================================

COLUMN_MAPPING_AI_AGENT_ID = "column_mapping_agent"


class DualPathColumnMapping(DualPathDecisionService[dict]):
    """Dual-path column mapping service.

    Deterministic path: validate_manual_mapping (exact rule-based validation).
    AI path: LLM suggests column mappings based on column profiles and sample data.
    Both paths produce the same output schema (mapping dict with status and messages).
    """

    AGENT_ID = COLUMN_MAPPING_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Column Mapping Agent"

    def _deterministic_path(self, inputs: dict) -> dict:
        """Run deterministic column mapping validation."""
        profile: ColumnProfile = inputs["profile"]
        columns: list[ColumnProfileColumn] = inputs["columns"]
        mapping_json: ManualMappingJson = inputs["mapping_json"]
        status, messages, canonical_mapping = validate_manual_mapping(
            profile=profile, columns=columns, mapping_json=mapping_json,
        )
        return {
            "status": status.value,
            "messages": messages,
            "canonical_mapping": canonical_mapping,
            "decision_source": "deterministic",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        columns: list[ColumnProfileColumn] = inputs["columns"]
        columns_for_prompt = [
            {
                "column_id": str(col.id),
                "original_column_name": col.original_column_name,
                "normalized_column_name": col.normalized_column_name,
                "inferred_data_type": col.inferred_data_type.value,
                "sample_values": col.sample_values_json[:5],
            }
            for col in columns
        ]
        existing_mapping = inputs.get("mapping_json")
        current_mapping = {
            "search_term": existing_mapping.search_term if existing_mapping else None,
            "search_volume": existing_mapping.search_volume if existing_mapping else None,
            "competitor_rank_columns": list(existing_mapping.competitor_rank_columns) if existing_mapping and existing_mapping.competitor_rank_columns else [],
        } if existing_mapping else None

        system = (
            "You are the AdSurf Column Mapping Agent. "
            "Your job is to suggest column mappings for Amazon competitor keyword files. "
            f"{safety_prompt_snippet()}"
            "You suggest mappings only — they must be reviewed by a human before approval. "
            "Return JSON only. "
            "Every output must include decision_source='ai' and requires_human_approval=true."
        )
        user = {
            "task": "suggest_column_mapping",
            "available_columns": columns_for_prompt,
            "current_mapping": current_mapping,
            "mapping_rules": {
                "search_term": "Must be a text column with search terms/keywords, not purely numeric.",
                "search_volume": "Must be a numeric column representing search volume.",
                "competitor_rank_columns": "1-10 numeric columns representing competitor ranks.",
            },
            "required_output_shape": {
                "suggested_mapping": {
                    "search_term": "original_column_name or null",
                    "search_volume": "original_column_name or null",
                    "competitor_rank_columns": ["original_column_name", "..."],
                    "confidence": "high | medium | low",
                    "reasoning": "brief explanation of mapping choices",
                },
                "validation_messages": [{"severity": "error | warning | info", "code": "...", "message": "..."}],
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
        mapping = ai_json.get("suggested_mapping", {})
        if not mapping:
            errors.append("AI output must include suggested_mapping.")
        if ai_json.get("decision_source") != "ai":
            errors.append("decision_source must be 'ai'.")
        if ai_json.get("requires_human_approval") is not True:
            errors.append("requires_human_approval must be true.")
        if ai_json.get("executes_live_amazon_change") is not False:
            errors.append("executes_live_amazon_change must be false.")
        if not mapping.get("search_term"):
            errors.append("suggested_mapping.search_term is required.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> dict:
        mapping = ai_json.get("suggested_mapping", {})
        return {
            "canonical_mapping": {
                "search_term": mapping.get("search_term"),
                "search_volume": mapping.get("search_volume"),
                "competitor_rank_columns": mapping.get("competitor_rank_columns", []),
            },
            "messages": ai_json.get("validation_messages", []),
            "status": "valid",
            "confidence": mapping.get("confidence", "medium"),
            "reasoning": mapping.get("reasoning", ""),
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _empty_result(self) -> dict:
        return {
            "status": "invalid",
            "messages": [{"severity": "error", "code": "AI_MAPPING_FAILED", "message": "AI column mapping could not be generated."}],
            "canonical_mapping": {},
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }
