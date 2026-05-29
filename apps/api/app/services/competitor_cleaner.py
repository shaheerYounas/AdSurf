import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import (
    CompetitorCleanedRow,
    CompetitorUpload,
    CompetitorUploadStatus,
)


MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 100_000
SEARCH_VOLUME_PATTERNS = [
    re.compile(r"search\s*volume", re.IGNORECASE),
    re.compile(r"monthly\s*search", re.IGNORECASE),
    re.compile(r"avg\s*monthly\s*search", re.IGNORECASE),
    re.compile(r"sv$", re.IGNORECASE),
]
RANK_PATTERNS = [
    re.compile(r"organic\s*rank", re.IGNORECASE),
    re.compile(r"natural\s*rank", re.IGNORECASE),
    re.compile(r"competitor\s*rank", re.IGNORECASE),
    re.compile(r"org\s*rank", re.IGNORECASE),
]
TERM_PATTERNS = [
    re.compile(r"search\s*term", re.IGNORECASE),
    re.compile(r"keyword", re.IGNORECASE),
    re.compile(r"targeting", re.IGNORECASE),
    re.compile(r"customer\s*search\s*term", re.IGNORECASE),
    re.compile(r"query", re.IGNORECASE),
]


@dataclass(frozen=True)
class CleanedResult:
    upload: CompetitorUpload
    rows: list[CompetitorCleanedRow]
    detected_columns: list[dict]
    warnings: list[dict]


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip().lower())


class CompetitorCleanerService:
    def __init__(self, repository: CompetitorCleanedRepository) -> None:
        self._repository = repository

    def process(
        self,
        *,
        upload: CompetitorUpload,
        content: bytes,
    ) -> CleanedResult:
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ApiError(
                code="COMPETITOR_FILE_TOO_LARGE",
                message="Competitor file exceeds the 10 MB size limit.",
                status_code=400,
            )

        self._repository.update_upload_status(
            workspace_id=upload.workspace_id,
            upload_id=upload.id,
            status=CompetitorUploadStatus.PROCESSING,
        )

        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            self._repository.update_upload_status(
                workspace_id=upload.workspace_id,
                upload_id=upload.id,
                status=CompetitorUploadStatus.FAILED,
                error_message="CSV must be valid UTF-8 encoding.",
            )
            raise ApiError(
                code="COMPETITOR_CSV_ENCODING_ERROR",
                message="CSV must be valid UTF-8 encoding.",
                status_code=400,
            ) from exc

        if not text.strip():
            self._repository.update_upload_status(
                workspace_id=upload.workspace_id,
                upload_id=upload.id,
                status=CompetitorUploadStatus.FAILED,
                error_message="Uploaded file is empty.",
            )
            raise ApiError(
                code="COMPETITOR_CSV_EMPTY",
                message="Uploaded file is empty.",
                status_code=400,
            )

        reader = csv.reader(io.StringIO(text))
        try:
            raw_headers = next(reader)
        except StopIteration as exc:
            self._repository.update_upload_status(
                workspace_id=upload.workspace_id,
                upload_id=upload.id,
                status=CompetitorUploadStatus.FAILED,
                error_message="File has no header row.",
            )
            raise ApiError(
                code="COMPETITOR_CSV_NO_HEADERS",
                message="CSV file must contain a header row.",
                status_code=400,
            ) from exc

        headers = [h.strip() for h in raw_headers]
        normalized_headers = [_normalize_header(h) for h in headers]

        warnings: list[dict] = []
        search_volume_index = self._detect_column(normalized_headers, SEARCH_VOLUME_PATTERNS)
        if search_volume_index is None:
            warnings.append({
                "code": "SEARCH_VOLUME_COLUMN_NOT_FOUND",
                "message": "Could not auto-detect a search volume column. The file may not contain monthly search volume data.",
            })

        term_index = self._detect_column(normalized_headers, TERM_PATTERNS)
        if term_index is None:
            warnings.append({
                "code": "SEARCH_TERM_COLUMN_NOT_FOUND",
                "message": "Could not auto-detect a search term / keyword column. Rows will be stored without search terms.",
            })

        rank_indices = self._detect_rank_columns(normalized_headers, RANK_PATTERNS)
        if not rank_indices:
            warnings.append({
                "code": "RANK_COLUMNS_NOT_FOUND",
                "message": "Could not auto-detect any organic rank columns. The file may not contain competitor ranking data.",
            })

        detected_columns: list[dict] = []
        for index, header in enumerate(headers):
            detected_columns.append({
                "original_column_name": header,
                "normalized_column_name": normalized_headers[index],
                "column_index": index,
                "is_search_volume": index == search_volume_index,
                "is_search_term": index == term_index,
                "is_rank": index in rank_indices,
            })

        cleaned_rows: list[CompetitorCleanedRow] = []
        now = datetime.now(UTC)
        row_number = 2
        for values in reader:
            if len(cleaned_rows) >= MAX_ROWS:
                warnings.append({
                    "code": "ROW_LIMIT_REACHED",
                    "message": f"Only the first {MAX_ROWS} rows were processed.",
                })
                break

            search_term = self._extract_value(values, term_index)
            search_volume = self._parse_decimal(self._extract_value(values, search_volume_index))

            rank_values: list[dict] = []
            for rank_index in rank_indices:
                raw_value = self._extract_value(values, rank_index)
                numeric = self._parse_decimal(raw_value)
                rank_values.append({
                    "column_name": headers[rank_index] if rank_index < len(headers) else f"column_{rank_index + 1}",
                    "column_index": rank_index,
                    "raw_value": raw_value,
                    "numeric_value": str(numeric) if numeric is not None else None,
                })

            raw_metrics = {}
            for index, value in enumerate(values):
                col_name = headers[index] if index < len(headers) else f"column_{index + 1}"
                parsed = self._parse_decimal(value)
                raw_metrics[col_name] = str(parsed) if parsed is not None else (value.strip() if value.strip() else None)

            cleaned_rows.append(CompetitorCleanedRow(
                id=uuid4(),
                workspace_id=upload.workspace_id,
                competitor_upload_id=upload.id,
                row_number=row_number,
                search_term=search_term,
                search_volume=float(search_volume) if search_volume is not None else None,
                competitor_rank_values_json=rank_values,
                raw_metrics_json=raw_metrics,
                created_at=now,
            ))
            row_number += 1

        if not cleaned_rows:
            self._repository.update_upload_status(
                workspace_id=upload.workspace_id,
                upload_id=upload.id,
                status=CompetitorUploadStatus.FAILED,
                error_message="No data rows found after the header.",
            )
            raise ApiError(
                code="COMPETITOR_CSV_NO_ROWS",
                message="No data rows found after the header row.",
                status_code=400,
            )

        cleaned_column_count = 1 + len(rank_indices) + (1 if term_index is not None else 0)

        self._repository.insert_rows(rows=cleaned_rows)
        updated = self._repository.update_upload_status(
            workspace_id=upload.workspace_id,
            upload_id=upload.id,
            status=CompetitorUploadStatus.SUCCEEDED,
            row_count=len(cleaned_rows),
            cleaned_column_count=cleaned_column_count,
            detected_columns_json=detected_columns,
            warnings_json=warnings,
        )

        return CleanedResult(
            upload=updated,
            rows=cleaned_rows,
            detected_columns=detected_columns,
            warnings=warnings,
        )

    @staticmethod
    def _detect_column(normalized_headers: list[str], patterns: list[re.Pattern]) -> int | None:
        for index, header in enumerate(normalized_headers):
            for pattern in patterns:
                if pattern.search(header):
                    return index
        return None

    @staticmethod
    def _detect_rank_columns(normalized_headers: list[str], patterns: list[re.Pattern]) -> list[int]:
        indices: list[int] = []
        for index, header in enumerate(normalized_headers):
            for pattern in patterns:
                if pattern.search(header):
                    indices.append(index)
                    break
        return indices

    @staticmethod
    def _extract_value(values: list[str], index: int | None) -> str | None:
        if index is None or index >= len(values):
            return None
        raw = values[index]
        if not raw or not raw.strip():
            return None
        return raw.strip()

    @staticmethod
    def _parse_decimal(value: str | None):
        if value is None:
            return None
        cleaned = value.strip().replace(",", "").replace("%", "")
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None