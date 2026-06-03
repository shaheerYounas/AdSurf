import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import (
    ACCEPTED_UPLOAD_EXTENSIONS,
    ACCEPTED_UPLOAD_MIME_TYPES,
    MAX_PARSED_UPLOAD_COLUMNS,
    MAX_PARSED_UPLOAD_ROWS,
    MAX_UPLOAD_FILE_SIZE_BYTES,
)
from apps.api.app.schemas.upload_parsing import ParsedUploadResult, ParsedUploadRow, UploadParseError


XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL_NS = {"rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
EXCEL_EPOCH = datetime(1899, 12, 30)
BUILTIN_DATE_FORMAT_IDS = set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47} | set(range(50, 59))


@dataclass(frozen=True)
class ParserLimits:
    max_file_size_bytes: int = MAX_UPLOAD_FILE_SIZE_BYTES
    max_rows: int = MAX_PARSED_UPLOAD_ROWS
    max_columns: int = MAX_PARSED_UPLOAD_COLUMNS


class UploadParser:
    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def parse(self, *, content: bytes, original_filename: str, mime_type: str) -> ParsedUploadResult:
        if len(content) > self._limits.max_file_size_bytes:
            raise ApiError(code="UPLOAD_FILE_TOO_LARGE", message="Upload file exceeds the MVP size limit.", status_code=400)
        extension = _extension_for(original_filename)
        if extension not in ACCEPTED_UPLOAD_EXTENSIONS:
            raise ApiError(code="UNSUPPORTED_UPLOAD_EXTENSION", message="Upload file extension is not supported.", status_code=400)
        if mime_type not in ACCEPTED_UPLOAD_MIME_TYPES:
            raise ApiError(code="UNSUPPORTED_UPLOAD_MIME_TYPE", message="Upload MIME type is not supported.", status_code=400)
        if extension == ".csv":
            return self._parse_csv(content)
        if extension == ".xlsx":
            return self._parse_xlsx(content)
        if extension == ".xls":
            return self._parse_xls(content)
        raise ApiError(code="UNSUPPORTED_UPLOAD_EXTENSION", message="Upload file extension is not supported.", status_code=400)

    def _parse_csv(self, content: bytes) -> ParsedUploadResult:
        text = _decode_utf8_sig(content)
        if not text.strip():
            raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded file is empty.", status_code=400)
        reader = csv.reader(io.StringIO(text))
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded file is empty.", status_code=400) from exc
        headers = [_normalize_header(header, index) for index, header in enumerate(headers)]
        _enforce_column_limit(len(headers), self._limits.max_columns)
        rows: list[ParsedUploadRow] = []
        errors: list[UploadParseError] = []
        for row_index, values in enumerate(reader, start=2):
            _enforce_row_limit(len(rows) + 1, self._limits.max_rows)
            if len(values) > len(headers):
                errors.append(
                    UploadParseError(
                        row_number=row_index,
                        error_code="ROW_HAS_TOO_MANY_COLUMNS",
                        error_message="Row has more values than the header row.",
                        raw_value_json=values,
                    )
                )
                continue
            normalized = _row_from_values(headers, values)
            rows.append(ParsedUploadRow(row_number=row_index, row_data_json=normalized, row_hash=stable_row_hash(normalized)))
        if not headers:
            raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded file has no columns.", status_code=400)
        return ParsedUploadResult(
            detected_file_type="csv",
            total_rows=len(rows),
            total_columns=len(headers),
            rows=rows,
            errors=errors,
        )

    def _parse_xlsx(self, content: bytes) -> ParsedUploadResult:
        if not content:
            raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded file is empty.", status_code=400)
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
                rels_xml = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                shared_strings = _read_shared_strings(archive)
                date_style_indexes = _read_date_style_indexes(archive)
                sheets = _workbook_sheets(workbook_xml, rels_xml)
                detected_sheet_names = [sheet_name for sheet_name, _ in sheets]
                candidates: list[tuple[str, str, int]] = []
                for sheet_name, sheet_path in sheets:
                    parsed = _parse_sheet_stream(
                        archive=archive,
                        sheet_path=sheet_path,
                        shared_strings=shared_strings,
                        date_style_indexes=date_style_indexes,
                        detected_file_type="xlsx",
                        detected_sheet_names=detected_sheet_names,
                        selected_sheet_name=sheet_name,
                        limits=self._limits,
                    )
                    if parsed.total_columns > 0:
                        candidates.append((sheet_name, sheet_path, parsed.total_columns))
                if not candidates:
                    raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded workbook has no non-empty sheets.", status_code=400)
                selected = _select_best_candidate(candidates)
                return _parse_sheet_stream(
                    archive=archive,
                    sheet_path=selected[1],
                    shared_strings=shared_strings,
                    date_style_indexes=date_style_indexes,
                    detected_file_type="xlsx",
                    detected_sheet_names=detected_sheet_names,
                    selected_sheet_name=selected[0],
                    limits=self._limits,
                )
        except KeyError as exc:
            raise ApiError(code="UPLOAD_PARSE_INVALID_XLSX", message="XLSX workbook is missing required parts.", status_code=400) from exc
        except zipfile.BadZipFile as exc:
            raise ApiError(code="UPLOAD_PARSE_INVALID_XLSX", message="XLSX workbook could not be opened.", status_code=400) from exc
        raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded workbook has no non-empty sheets.", status_code=400)

    def _parse_xls(self, content: bytes) -> ParsedUploadResult:
        try:
            import xlrd  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ApiError(
                code="UPLOAD_PARSE_XLS_DEPENDENCY_MISSING",
                message="Legacy XLS parsing requires the xlrd dependency.",
                status_code=503,
            ) from exc
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
        sheet_names = workbook.sheet_names()
        for sheet_name in sheet_names:
            sheet = workbook.sheet_by_name(sheet_name)
            raw_rows = [[sheet.cell_value(row_index, col_index) for col_index in range(sheet.ncols)] for row_index in range(sheet.nrows)]
            parsed = _rows_from_matrix(
                raw_rows=raw_rows,
                detected_file_type="xls",
                detected_sheet_names=sheet_names,
                selected_sheet_name=sheet_name,
                limits=self._limits,
            )
            if parsed.total_columns > 0:
                return parsed
        raise ApiError(code="UPLOAD_PARSE_EMPTY_FILE", message="Uploaded workbook has no non-empty sheets.", status_code=400)


def stable_row_hash(row_data: dict) -> str:
    payload = json.dumps(row_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_utf8_sig(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(code="UPLOAD_PARSE_ENCODING_ERROR", message="CSV must be valid UTF-8.", status_code=400) from exc


def _rows_from_matrix(
    *,
    raw_rows: list[list[Any]],
    detected_file_type: str,
    detected_sheet_names: list[str],
    selected_sheet_name: str,
    limits: ParserLimits,
) -> ParsedUploadResult:
    non_empty_rows = [row for row in raw_rows if any(_cell_to_json_value(value) is not None for value in row)]
    if not non_empty_rows:
        return ParsedUploadResult(
            detected_file_type=detected_file_type,
            detected_sheet_names=detected_sheet_names,
            selected_sheet_name=selected_sheet_name,
            total_rows=0,
            total_columns=0,
            rows=[],
        )
    headers = [_normalize_header(str(_cell_to_json_value(value) or ""), index) for index, value in enumerate(non_empty_rows[0])]
    _enforce_column_limit(len(headers), limits.max_columns)
    rows: list[ParsedUploadRow] = []
    for row_number, raw_values in enumerate(non_empty_rows[1:], start=2):
        _enforce_row_limit(len(rows) + 1, limits.max_rows)
        normalized = _row_from_values(headers, [_cell_to_json_value(value) for value in raw_values])
        rows.append(ParsedUploadRow(row_number=row_number, row_data_json=normalized, row_hash=stable_row_hash(normalized)))
    return ParsedUploadResult(
        detected_file_type=detected_file_type,
        detected_sheet_names=detected_sheet_names,
        selected_sheet_name=selected_sheet_name,
        total_rows=len(rows),
        total_columns=len(headers),
        rows=rows,
    )


def _parse_sheet_stream(
    *,
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    date_style_indexes: set[int] | None,
    detected_file_type: str,
    detected_sheet_names: list[str],
    selected_sheet_name: str,
    limits: ParserLimits,
) -> ParsedUploadResult:
    headers: list[str] | None = None
    rows: list[ParsedUploadRow] = []
    for raw_values in _iter_sheet_rows(archive, sheet_path, shared_strings, date_style_indexes or set(), limits):
        values = [_cell_to_json_value(value) for value in raw_values]
        if not any(value is not None for value in values):
            continue
        if headers is None:
            headers = [_normalize_header(str(value or ""), index) for index, value in enumerate(values)]
            _enforce_column_limit(len(headers), limits.max_columns)
            continue
        _enforce_row_limit(len(rows) + 1, limits.max_rows)
        normalized = _row_from_values(headers, values)
        row_number = len(rows) + 2
        rows.append(ParsedUploadRow(row_number=row_number, row_data_json=normalized, row_hash=stable_row_hash(normalized)))
    if headers is None:
        return ParsedUploadResult(
            detected_file_type=detected_file_type,
            detected_sheet_names=detected_sheet_names,
            selected_sheet_name=selected_sheet_name,
            total_rows=0,
            total_columns=0,
            rows=[],
        )
    return ParsedUploadResult(
        detected_file_type=detected_file_type,
        detected_sheet_names=detected_sheet_names,
        selected_sheet_name=selected_sheet_name,
        total_rows=len(rows),
        total_columns=len(headers),
        rows=rows,
    )


def _row_from_values(headers: list[str], values: list[Any]) -> dict:
    normalized: dict[str, Any] = {}
    for index, header in enumerate(headers):
        value = values[index] if index < len(values) else None
        normalized[header] = _cell_to_json_value(value)
    return normalized


def _cell_to_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped != "" else None
    return value


def _normalize_header(header: str, index: int) -> str:
    normalized = header.strip()
    return normalized if normalized else f"column_{index + 1}"


def _enforce_row_limit(count: int, max_rows: int) -> None:
    if count > max_rows:
        raise ApiError(code="UPLOAD_PARSE_ROW_LIMIT_EXCEEDED", message="Parsed row limit exceeded.", status_code=400)


def _enforce_column_limit(count: int, max_columns: int) -> None:
    if count > max_columns:
        raise ApiError(code="UPLOAD_PARSE_COLUMN_LIMIT_EXCEEDED", message="Parsed column limit exceeded.", status_code=400)


def _extension_for(filename: str) -> str:
    dot_index = filename.rfind(".")
    return filename[dot_index:].lower() if dot_index >= 0 else ""


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for item in root.findall("main:si", XLSX_NS):
        text_parts = [node.text or "" for node in item.findall(".//main:t", XLSX_NS)]
        strings.append("".join(text_parts))
    return strings


def _read_date_style_indexes(archive: zipfile.ZipFile) -> set[int]:
    try:
        root = ElementTree.fromstring(archive.read("xl/styles.xml"))
    except KeyError:
        return set()
    custom_date_format_ids = {
        int(node.attrib["numFmtId"])
        for node in root.findall(".//main:numFmt", XLSX_NS)
        if node.attrib.get("numFmtId", "").isdigit() and _looks_like_excel_date_format(node.attrib.get("formatCode", ""))
    }
    date_format_ids = BUILTIN_DATE_FORMAT_IDS | custom_date_format_ids
    style_indexes: set[int] = set()
    cell_xfs = root.find("main:cellXfs", XLSX_NS)
    if cell_xfs is None:
        return style_indexes
    for index, xf in enumerate(cell_xfs.findall("main:xf", XLSX_NS)):
        num_fmt_id = xf.attrib.get("numFmtId")
        if num_fmt_id and num_fmt_id.isdigit() and int(num_fmt_id) in date_format_ids:
            style_indexes.add(index)
    return style_indexes


def _looks_like_excel_date_format(format_code: str) -> bool:
    lowered = re.sub(r'".*?"|\[.*?\]', "", format_code.lower())
    return any(token in lowered for token in ("yy", "mm", "dd", "hh", "ss")) and "%" not in lowered


def _workbook_sheets(workbook_xml: ElementTree.Element, rels_xml: ElementTree.Element) -> list[tuple[str, str]]:
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_xml.findall("rel:Relationship", REL_NS)
        if "Id" in rel.attrib and "Target" in rel.attrib
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook_xml.findall(".//main:sheet", XLSX_NS):
        name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        if rel_id and rel_id in rel_targets:
            target = rel_targets[rel_id]
            path = str(PurePosixPath("xl") / target) if not target.startswith("/") and not target.startswith("xl/") else target.lstrip("/")
            sheets.append((name, path))
    return sheets


def _iter_sheet_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    date_style_indexes: set[int],
    limits: ParserLimits,
):
    with archive.open(sheet_path) as sheet_file:
        for _, row in ElementTree.iterparse(sheet_file, events=("end",)):
            if row.tag != f"{{{XLSX_NS['main']}}}row":
                continue
            yield _read_xlsx_row(row, shared_strings, date_style_indexes, limits)
            row.clear()


def _read_xlsx_row(row: ElementTree.Element, shared_strings: list[str], date_style_indexes: set[int], limits: ParserLimits) -> list[Any]:
    values_by_column: dict[int, Any] = {}
    for cell in row.findall("main:c", XLSX_NS):
        column_index = _column_index(cell.attrib.get("r", "A1"))
        _enforce_column_limit(column_index + 1, limits.max_columns)
        values_by_column[column_index] = _xlsx_cell_value(cell, shared_strings, date_style_indexes)
    if not values_by_column:
        return []
    max_column = max(values_by_column)
    return [values_by_column.get(index) for index in range(max_column + 1)]


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str], date_style_indexes: set[int]) -> Any:
    cell_type = cell.attrib.get("t")
    formula_node = cell.find("main:f", XLSX_NS)
    if formula_node is not None:
        return f"={formula_node.text}" if formula_node.text else None
    value_node = cell.find("main:v", XLSX_NS)
    if cell_type == "inlineStr":
        text_parts = [node.text or "" for node in cell.findall(".//main:t", XLSX_NS)]
        return "".join(text_parts)
    if value_node is None or value_node.text is None:
        return None
    raw_value = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw_value)] if raw_value.isdigit() and int(raw_value) < len(shared_strings) else raw_value
    if cell_type == "b":
        return raw_value == "1"
    try:
        number = float(raw_value)
        style_index = cell.attrib.get("s")
        if style_index and style_index.isdigit() and int(style_index) in date_style_indexes:
            return _excel_serial_to_iso(number)
        return int(number) if number.is_integer() else number
    except ValueError:
        return raw_value


def _excel_serial_to_iso(value: float) -> str:
    converted = EXCEL_EPOCH + timedelta(days=value)
    if converted.time() == datetime.min.time():
        return converted.date().isoformat()
    return converted.isoformat(timespec="seconds")


_BULK_SHEET_PRIORITY_NAMES = [
    "sponsored products campaigns",
    "sp search term report",
    "sponsored products search term report",
]

_SINGLE_SHEET_PRIORITY_NAMES = [
    "sponsored products search term",
    "sponsored products targeting",
    "sponsored products campaigns",
]


def _select_best_candidate(candidates: list[tuple[str, str, int]]) -> tuple[str, str, int]:
    """Select the most relevant sheet from multi-sheet workbooks.

    Prioritizes Sponsored Products Campaigns and SP Search Term Report sheets
    for bulk workbooks, and search term report sheets for single-sheet reports.
    Falls back to the sheet with the most columns.
    """
    names = {candidate[0].strip().lower() for candidate in candidates}

    for priority_name in _BULK_SHEET_PRIORITY_NAMES:
        for candidate in candidates:
            if candidate[0].strip().lower() == priority_name:
                return candidate

    if len(candidates) == 1:
        return candidates[0]

    for priority_name in _SINGLE_SHEET_PRIORITY_NAMES:
        for candidate in candidates:
            if priority_name in candidate[0].strip().lower():
                return candidate

    # Fallback: sheet with most columns
    return max(candidates, key=lambda c: c[2])


def _column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha()).upper()
    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - ord("A") + 1)
    return max(index - 1, 0)
