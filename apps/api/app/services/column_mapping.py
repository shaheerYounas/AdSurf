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


MAX_COMPETITOR_RANK_COLUMNS = 10


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
