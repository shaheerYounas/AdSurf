import re
from datetime import date, datetime
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.column_mapping import ColumnMappingRepository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository
from apps.api.app.schemas.column_mapping import ColumnInferredDataType, ColumnProfileWithColumns
from apps.api.app.schemas.upload_parsing import UploadParseRun, UploadParseStatus


SAMPLE_LIMIT_PER_COLUMN = 20
ROWS_PAGE_SIZE = 500


class ColumnDiscoveryService:
    def __init__(
        self,
        *,
        parsing_repository: UploadParsingRepository,
        column_repository: ColumnMappingRepository,
    ) -> None:
        self._parsing_repository = parsing_repository
        self._column_repository = column_repository

    def generate_for_upload(self, *, workspace_id: UUID, upload_id: UUID) -> ColumnProfileWithColumns:
        parse_run = self._latest_succeeded_parse_run(workspace_id=workspace_id, upload_id=upload_id)
        existing = self._column_repository.get_profile_by_parse_run(workspace_id=workspace_id, parse_run_id=parse_run.id)
        if existing is not None:
            profile, columns = existing
            return ColumnProfileWithColumns(profile=profile, columns=columns)

        columns = _discover_columns(parse_run=parse_run, parsing_repository=self._parsing_repository)
        profile, profile_columns = self._column_repository.create_profile(
            parse_run=parse_run,
            total_columns=len(columns),
            total_rows_sampled=parse_run.parsed_rows_count,
            columns=columns,
        )
        return ColumnProfileWithColumns(profile=profile, columns=profile_columns)

    def get_for_upload(self, *, workspace_id: UUID, upload_id: UUID) -> ColumnProfileWithColumns | None:
        existing = self._column_repository.get_profile_for_upload(workspace_id=workspace_id, upload_id=upload_id)
        if existing is None:
            return None
        profile, columns = existing
        return ColumnProfileWithColumns(profile=profile, columns=columns)

    def _latest_succeeded_parse_run(self, *, workspace_id: UUID, upload_id: UUID) -> UploadParseRun:
        runs = self._parsing_repository.list_runs(workspace_id=workspace_id, upload_id=upload_id)
        for run in runs:
            if run.status == UploadParseStatus.SUCCEEDED:
                return run
        raise ApiError(
            code="COLUMN_PROFILE_PARSE_RUN_REQUIRED",
            message="A succeeded parse run is required before column discovery.",
            status_code=409,
        )


def normalize_column_name(value: str) -> str:
    lowered = value.strip().lower()
    collapsed = re.sub(r"\s+", " ", lowered)
    without_punctuation = re.sub(r"[^\w\s]", "", collapsed)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def _discover_columns(*, parse_run: UploadParseRun, parsing_repository: UploadParsingRepository) -> list[dict]:
    rows, total = parsing_repository.list_rows(workspace_id=parse_run.workspace_id, parse_run_id=parse_run.id, page=1, page_size=ROWS_PAGE_SIZE)
    if total == 0:
        return []
    column_names = list(rows[0].row_data_json.keys()) if rows else []
    stats = {
        column_name: {
            "original_column_name": column_name,
            "normalized_column_name": normalize_column_name(column_name),
            "column_index": index,
            "non_null_count": 0,
            "sample_values_json": [],
            "values_for_type": [],
        }
        for index, column_name in enumerate(column_names)
    }
    page = 1
    while rows:
        for row in rows:
            for column_name in column_names:
                value = row.row_data_json.get(column_name)
                if value is None:
                    continue
                stats[column_name]["non_null_count"] += 1
                stats[column_name]["values_for_type"].append(value)
                if len(stats[column_name]["sample_values_json"]) < SAMPLE_LIMIT_PER_COLUMN:
                    stats[column_name]["sample_values_json"].append(value)
        if page * ROWS_PAGE_SIZE >= total:
            break
        page += 1
        rows, _ = parsing_repository.list_rows(
            workspace_id=parse_run.workspace_id,
            parse_run_id=parse_run.id,
            page=page,
            page_size=ROWS_PAGE_SIZE,
        )

    discovered: list[dict] = []
    for column_name in column_names:
        column = stats[column_name]
        discovered.append(
            {
                "original_column_name": column["original_column_name"],
                "normalized_column_name": column["normalized_column_name"],
                "column_index": column["column_index"],
                "non_null_count": column["non_null_count"],
                "sample_values_json": column["sample_values_json"],
                "inferred_data_type": infer_data_type(column["values_for_type"]),
            }
        )
    return discovered


def infer_data_type(values: list) -> ColumnInferredDataType:
    non_null = [value for value in values if value is not None]
    if not non_null:
        return ColumnInferredDataType.UNKNOWN
    if all(isinstance(value, bool) for value in non_null):
        return ColumnInferredDataType.BOOLEAN
    if all(isinstance(value, int) and not isinstance(value, bool) for value in non_null):
        return ColumnInferredDataType.INTEGER
    if all(isinstance(value, int | float) and not isinstance(value, bool) for value in non_null):
        return ColumnInferredDataType.DECIMAL if any(isinstance(value, float) and not value.is_integer() for value in non_null) else ColumnInferredDataType.INTEGER
    if all(isinstance(value, date | datetime) for value in non_null):
        return ColumnInferredDataType.DATE
    if all(isinstance(value, str) for value in non_null):
        if all(_is_boolean_string(value) for value in non_null):
            return ColumnInferredDataType.BOOLEAN
        if all(_is_date_string(value) for value in non_null):
            return ColumnInferredDataType.DATE
        return ColumnInferredDataType.TEXT
    return ColumnInferredDataType.TEXT


def _is_boolean_string(value: str) -> bool:
    return value.strip().lower() in {"true", "false", "yes", "no"}


def _is_date_string(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            datetime.strptime(stripped, fmt)
            return True
        except ValueError:
            continue
    return False
