"""Bulk product profile import service.

This service parses CSV/XLSX product lists, maps common seller-facing headers
onto the product profile contract, validates each row, detects duplicates, and
returns a preview. It never creates product profiles; commit remains an explicit
API step after human review.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4
from xml.etree import ElementTree

from apps.api.app.schemas.bulk_product_import import (
    BulkImportConflictStrategy,
    BulkImportRowStatus,
    BulkProductRow,
    BulkProductRowValidationError,
)


DEFAULT_TARGET_ACOS = Decimal("0.5000")
DEFAULT_BUDGET = Decimal("10.0000")
DEFAULT_BID = Decimal("1.0000")

ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}

MARKETPLACE_ALIASES = {
    "US": "US",
    "USA": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "AMERICA": "US",
    "CA": "CA",
    "CANADA": "CA",
    "UK": "UK",
    "GB": "UK",
    "UNITED KINGDOM": "UK",
    "DE": "DE",
    "GERMANY": "DE",
    "FR": "FR",
    "FRANCE": "FR",
    "IT": "IT",
    "ITALY": "IT",
    "ES": "ES",
    "SPAIN": "ES",
    "NL": "NL",
    "NETHERLANDS": "NL",
    "SE": "SE",
    "SWEDEN": "SE",
    "PL": "PL",
    "POLAND": "PL",
    "BE": "BE",
    "BELGIUM": "BE",
    "JP": "JP",
    "JAPAN": "JP",
    "AU": "AU",
    "AUSTRALIA": "AU",
    "MX": "MX",
    "MEXICO": "MX",
    "BR": "BR",
    "BRAZIL": "BR",
}

MARKETPLACE_CURRENCY = {
    "US": "USD",
    "CA": "CAD",
    "UK": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "NL": "EUR",
    "SE": "SEK",
    "PL": "PLN",
    "BE": "EUR",
    "JP": "JPY",
    "AU": "AUD",
    "MX": "MXN",
    "BR": "BRL",
}

KNOWN_FIELDS = {
    "product_name",
    "asin",
    "sku",
    "marketplace",
    "currency",
    "target_acos",
    "default_budget",
    "default_bid",
    "brand",
    "category",
    "notes",
}


def _normalise_header_for_matching(header: str) -> str:
    normalized = header.replace("\ufeff", "").replace("%", " percent ")
    normalized = re.sub(r"[_\-/]+", " ", normalized.casefold())
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


_COLUMN_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "product_name": (
        "product name",
        "product_name",
        "name",
        "title",
        "product title",
        "item name",
        "item_name",
    ),
    "asin": (
        "asin",
        "product asin",
        "product_asin",
        "child asin",
        "child_asin",
        "advertised asin",
        "advertised_asin",
        "advertised product asin",
        "advertised_product_asin",
    ),
    "sku": (
        "sku",
        "seller sku",
        "seller_sku",
        "merchant sku",
        "merchant_sku",
        "product sku",
        "product_sku",
        "advertised sku",
        "advertised_sku",
    ),
    "marketplace": (
        "marketplace",
        "market",
        "country",
        "region",
    ),
    "currency": (
        "currency",
        "currency code",
        "currency_code",
    ),
    "target_acos": (
        "target acos",
        "target_acos",
        "acos target",
        "acos_target",
        "target acos %",
        "target acos percent",
        "target acos pct",
    ),
    "default_budget": (
        "default budget",
        "default_budget",
        "daily budget",
        "daily_budget",
        "budget",
        "campaign budget",
        "campaign_budget",
    ),
    "default_bid": (
        "default bid",
        "default_bid",
        "bid",
        "starting bid",
        "starting_bid",
        "keyword bid",
        "keyword_bid",
    ),
    "brand": (
        "brand",
        "brand name",
        "brand_name",
    ),
    "category": (
        "category",
        "product category",
        "product_category",
    ),
    "notes": (
        "notes",
        "note",
        "comments",
        "comment",
    ),
}

COLUMN_ALIASES: dict[str, str] = {
    _normalise_header_for_matching(alias): canonical
    for canonical, aliases in _COLUMN_ALIAS_GROUPS.items()
    for alias in aliases
}


class BulkProductImportParseError(ValueError):
    """User-safe parse error for product import files."""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class RawProductImportRow:
    row_number: int
    raw_row: dict[str, str]


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_field_for_header(header: str) -> str:
    """Return the canonical product field for a raw/unique header."""

    base_header = re.sub(r"\s+\(\d+\)$", "", header.strip())
    return COLUMN_ALIASES.get(_normalise_header_for_matching(base_header), "")


def parse_file_to_rows(content: bytes, filename: str) -> tuple[list[RawProductImportRow], dict[str, str]]:
    """Parse CSV/TSV/XLSX bytes into source-numbered rows and a header map."""

    lower = filename.lower()
    if lower.endswith(".xlsx"):
        raw_rows, headers = _parse_xlsx(content)
    elif lower.endswith((".csv", ".tsv")):
        raw_rows, headers = _parse_csv(content, force_tab=lower.endswith(".tsv"))
    else:
        raise BulkProductImportParseError(
            "UNSUPPORTED_FILE_TYPE",
            "Only CSV, TSV, and XLSX files are supported for bulk product import.",
            status_code=400,
        )

    if not headers:
        raise BulkProductImportParseError("NO_HEADERS", "The file must contain a header row.")
    if not raw_rows:
        raise BulkProductImportParseError("NO_DATA_ROWS", "The file must contain at least one product row.")

    detected_mapping = {header: canonical_field_for_header(header) for header in headers}
    return raw_rows, detected_mapping


def validate_row(
    row_number: int,
    raw: dict[str, str],
    column_mapping: dict[str, str],
    workspace_defaults: dict[str, Any],
) -> BulkProductRow:
    """Map raw headers to canonical fields, validate, and return a row preview."""

    mapped: dict[str, str] = {}
    for original_col, value in raw.items():
        canonical = column_mapping.get(original_col, "")
        raw_value = _cell_to_text(value)
        if canonical and canonical in KNOWN_FIELDS and (canonical not in mapped or (not mapped[canonical] and raw_value.strip())):
            mapped[canonical] = raw_value.strip()

    errors: list[BulkProductRowValidationError] = []

    product_name_raw = mapped.get("product_name", "").strip()
    product_name = sanitize_preview_value(product_name_raw) if product_name_raw else ""
    if not product_name_raw:
        errors.append(_error("product_name", "Product name is required"))
    elif len(product_name) > 200:
        errors.append(_error("product_name", "Product name must be 200 characters or fewer", product_name_raw))

    asin_raw = mapped.get("asin", "").strip()
    asin = asin_raw.upper() if asin_raw else None
    if asin:
        if not ASIN_PATTERN.match(asin):
            errors.append(_error("asin", "ASIN must be exactly 10 uppercase letters/digits", asin_raw))
            asin = None

    sku_raw = mapped.get("sku", "").strip()
    sku = sanitize_preview_value(sku_raw) if sku_raw else None
    if sku and len(sku) > 100:
        errors.append(_error("sku", "SKU must be 100 characters or fewer", sku_raw))

    if not asin and not sku:
        errors.append(_error("asin", "ASIN or SKU is required so duplicate products can be detected"))

    marketplace_raw = mapped.get("marketplace", "").strip()
    marketplace = _normalise_marketplace(marketplace_raw) if marketplace_raw else "US"
    if marketplace_raw and marketplace is None:
        errors.append(_error("marketplace", "Marketplace is not supported", marketplace_raw))
        marketplace = marketplace_raw.upper()

    expected_currency = MARKETPLACE_CURRENCY.get(marketplace or "US", "USD")
    currency_raw = mapped.get("currency", "").strip()
    currency = currency_raw.upper() if currency_raw else expected_currency
    if currency and not re.fullmatch(r"[A-Z]{3}", currency):
        errors.append(_error("currency", "Currency must be a 3-letter ISO code", currency_raw))
    elif marketplace in MARKETPLACE_CURRENCY and currency != expected_currency:
        errors.append(_error("currency", f"Currency for marketplace {marketplace} must be {expected_currency}", currency_raw))

    target_acos = _target_acos_value(mapped.get("target_acos"), workspace_defaults, errors)
    default_budget = _money_value(
        "default_budget",
        mapped.get("default_budget"),
        workspace_defaults.get("default_budget", DEFAULT_BUDGET),
        errors,
    )
    default_bid = _money_value(
        "default_bid",
        mapped.get("default_bid"),
        workspace_defaults.get("default_bid", DEFAULT_BID),
        errors,
    )

    brand = _optional_text(mapped.get("brand"), max_length=200, field="brand", errors=errors)
    category = _optional_text(mapped.get("category"), max_length=100, field="category", errors=errors)
    notes = _optional_text(mapped.get("notes"), max_length=1000, field="notes", errors=errors)

    status = BulkImportRowStatus.VALID if not errors else BulkImportRowStatus.INVALID

    return BulkProductRow(
        id=uuid4(),
        row_number=row_number,
        status=status,
        product_name=product_name or None,
        asin=asin,
        sku=sku,
        marketplace=marketplace or "US",
        currency=currency or "USD",
        target_acos=target_acos,
        default_budget=default_budget,
        default_bid=default_bid,
        brand=brand,
        category=category,
        notes=notes,
        validation_errors=errors,
        raw_row_json={key: sanitize_preview_value(_cell_to_text(value).strip()) for key, value in raw.items()},
    )


def detect_file_duplicates(rows: list[BulkProductRow]) -> list[BulkProductRow]:
    """Mark duplicate ASIN, SKU, or same-name/different-identity rows."""

    seen_asins: dict[str, int] = {}
    seen_skus: dict[str, int] = {}
    seen_names: dict[str, tuple[int, str | None, str | None]] = {}
    result: list[BulkProductRow] = []

    for row in rows:
        if row.status == BulkImportRowStatus.INVALID:
            result.append(row)
            continue

        duplicate_error: BulkProductRowValidationError | None = None
        if row.asin:
            asin_key = row.asin.upper()
            if asin_key in seen_asins:
                duplicate_error = _error("asin", f"Duplicate ASIN in file (first seen at row {seen_asins[asin_key]})", row.asin)
            else:
                seen_asins[asin_key] = row.row_number

        if row.sku:
            sku_key = row.sku.upper()
            if sku_key in seen_skus:
                if duplicate_error is None:
                    duplicate_error = _error("sku", f"Duplicate SKU in file (first seen at row {seen_skus[sku_key]})", row.sku)
            else:
                seen_skus[sku_key] = row.row_number

        name_key = _identity_name_key(row.product_name)
        if name_key:
            previous = seen_names.get(name_key)
            current_identity = (row.asin, row.sku)
            if previous and (previous[1], previous[2]) != current_identity and duplicate_error is None:
                duplicate_error = _error(
                    "product_name",
                    f"Product name appears with a different ASIN/SKU (first seen at row {previous[0]})",
                    row.product_name,
                )
            elif previous is None:
                seen_names[name_key] = (row.row_number, row.asin, row.sku)

        if duplicate_error is not None:
            row = row.model_copy(
                update={
                    "status": BulkImportRowStatus.DUPLICATE_IN_FILE,
                    "validation_errors": [*row.validation_errors, duplicate_error],
                }
            )

        result.append(row)
    return result


class BulkProductImportService:
    """Parse, validate, deduplicate, and summarize product import previews."""

    def parse_and_validate(
        self,
        *,
        content: bytes,
        filename: str,
        workspace_defaults: dict[str, Any],
    ) -> tuple[list[BulkProductRow], dict[str, str], str]:
        file_hash = compute_file_hash(content)
        raw_rows, column_mapping = parse_file_to_rows(content, filename)

        validated = [
            validate_row(raw_row.row_number, raw_row.raw_row, column_mapping, workspace_defaults)
            for raw_row in raw_rows
        ]
        return detect_file_duplicates(validated), column_mapping, file_hash

    def check_workspace_conflicts(
        self,
        *,
        rows: list[BulkProductRow],
        existing_by_asin: dict[str, str | UUID],
        existing_by_sku: dict[str, str | UUID],
        conflict_strategy: BulkImportConflictStrategy,
    ) -> list[BulkProductRow]:
        result: list[BulkProductRow] = []
        existing_asins = {key.upper(): _uuid_or_none(value) for key, value in existing_by_asin.items()}
        existing_skus = {key.upper(): _uuid_or_none(value) for key, value in existing_by_sku.items()}

        for row in rows:
            if row.status != BulkImportRowStatus.VALID:
                result.append(row)
                continue

            asin_product_id = existing_asins.get(row.asin.upper()) if row.asin else None
            sku_product_id = existing_skus.get(row.sku.upper()) if row.sku else None
            existing_product_id = asin_product_id or sku_product_id

            if asin_product_id and sku_product_id and asin_product_id != sku_product_id:
                result.append(
                    row.model_copy(
                        update={
                            "status": BulkImportRowStatus.INVALID,
                            "validation_errors": [
                                *row.validation_errors,
                                _error("sku", "ASIN and SKU match different existing products; review this row manually", row.sku),
                            ],
                        }
                    )
                )
                continue

            if existing_product_id:
                if conflict_strategy == BulkImportConflictStrategy.UPDATE_EXISTING:
                    row = row.model_copy(update={"product_id": existing_product_id})
                else:
                    row = row.model_copy(
                        update={
                            "status": BulkImportRowStatus.ALREADY_EXISTS,
                            "product_id": existing_product_id,
                            "validation_errors": [
                                *row.validation_errors,
                                _error("asin", "Product already exists in workspace and will be skipped", row.asin or row.sku),
                            ],
                        }
                    )

            result.append(row)
        return result

    def summarise(self, rows: list[BulkProductRow]) -> dict[str, int]:
        counts: dict[str, int] = {status.value: 0 for status in BulkImportRowStatus}
        for row in rows:
            counts[row.status.value] += 1
        return counts


def sanitize_preview_value(value: str) -> str:
    """Make spreadsheet-formula-like values inert in previews/exports."""

    if value and value[0] in FORMULA_PREFIXES:
        return f"'{value}"
    return value


def _parse_csv(content: bytes, *, force_tab: bool = False) -> tuple[list[RawProductImportRow], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BulkProductImportParseError("INVALID_ENCODING", "CSV files must use UTF-8 encoding.") from exc
    if not text.strip():
        raise BulkProductImportParseError("EMPTY_FILE", "The uploaded file is empty.")

    delimiter = "\t" if force_tab else _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise BulkProductImportParseError("EMPTY_FILE", "The uploaded file is empty.") from exc
    except csv.Error as exc:
        raise BulkProductImportParseError("MALFORMED_CSV", f"CSV could not be parsed: {exc}") from exc

    headers = _dedupe_headers(raw_headers)
    rows: list[RawProductImportRow] = []
    try:
        for row_number, values in enumerate(reader, start=2):
            if len(values) > len(headers) and any(value.strip() for value in values[len(headers):]):
                raise BulkProductImportParseError(
                    "ROW_HAS_TOO_MANY_COLUMNS",
                    f"Row {row_number} has more values than the header row.",
                )
            values = values[: len(headers)] + [""] * max(0, len(headers) - len(values))
            if not any(_cell_to_text(value).strip() for value in values):
                continue
            rows.append(RawProductImportRow(row_number=row_number, raw_row=dict(zip(headers, values, strict=True))))
    except csv.Error as exc:
        raise BulkProductImportParseError("MALFORMED_CSV", f"CSV could not be parsed: {exc}") from exc

    return rows, headers


def _parse_xlsx(content: bytes) -> tuple[list[RawProductImportRow], list[str]]:
    if not content:
        raise BulkProductImportParseError("EMPTY_FILE", "The uploaded file is empty.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            rels_xml = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            shared_strings = _read_shared_strings(archive)
            candidates: list[tuple[int, int, list[RawProductImportRow], list[str]]] = []
            for sheet_index, (_, sheet_path) in enumerate(_workbook_sheets(workbook_xml, rels_xml)):
                rows, headers = _read_xlsx_sheet(archive, sheet_path, shared_strings)
                if headers:
                    mapped_count = sum(1 for header in headers if canonical_field_for_header(header))
                    candidates.append((mapped_count, -sheet_index, rows, headers))
    except KeyError as exc:
        raise BulkProductImportParseError("INVALID_XLSX", "XLSX workbook is missing required parts.") from exc
    except zipfile.BadZipFile as exc:
        raise BulkProductImportParseError("INVALID_XLSX", "XLSX workbook could not be opened.") from exc
    except ElementTree.ParseError as exc:
        raise BulkProductImportParseError("INVALID_XLSX", "XLSX workbook XML could not be parsed.") from exc

    if not candidates:
        raise BulkProductImportParseError("EMPTY_WORKBOOK", "Uploaded workbook has no non-empty sheets.")

    _, _, selected_rows, selected_headers = max(candidates, key=lambda candidate: (candidate[0], len(candidate[2]), candidate[1]))
    if not selected_rows:
        raise BulkProductImportParseError("NO_DATA_ROWS", "The workbook sheet must contain at least one product row.")
    return selected_rows, selected_headers


def _read_xlsx_sheet(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> tuple[list[RawProductImportRow], list[str]]:
    rows: list[RawProductImportRow] = []
    headers: list[str] | None = None

    with archive.open(sheet_path) as sheet_file:
        for _, row_el in ElementTree.iterparse(sheet_file, events=("end",)):
            if row_el.tag != f"{{{XLSX_NS['main']}}}row":
                continue
            if row_el.attrib.get("hidden") in {"1", "true", "TRUE"}:
                row_el.clear()
                continue

            row_number = _row_number(row_el)
            values = _read_xlsx_row(row_el, shared_strings)
            row_el.clear()
            if not any(_cell_to_text(value).strip() for value in values):
                continue

            if headers is None:
                headers = _dedupe_headers([_cell_to_text(value) for value in values])
                continue

            values = values[: len(headers)] + [""] * max(0, len(headers) - len(values))
            rows.append(RawProductImportRow(row_number=row_number, raw_row=dict(zip(headers, values, strict=True))))

    return rows, headers or []


def _read_xlsx_row(row_el: ElementTree.Element, shared_strings: list[str]) -> list[str]:
    values_by_column: dict[int, str] = {}
    for cell in row_el.findall("main:c", XLSX_NS):
        column_index = _column_index(cell.attrib.get("r", "A1"))
        values_by_column[column_index] = _xlsx_cell_value(cell, shared_strings)
    if not values_by_column:
        return []
    return [values_by_column.get(index, "") for index in range(max(values_by_column) + 1)]


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    formula_node = cell.find("main:f", XLSX_NS)
    if formula_node is not None:
        return f"={formula_node.text}" if formula_node.text else ""

    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", XLSX_NS))

    value_node = cell.find("main:v", XLSX_NS)
    if value_node is None or value_node.text is None:
        return ""
    raw_value = value_node.text

    if cell_type == "s":
        return shared_strings[int(raw_value)] if raw_value.isdigit() and int(raw_value) < len(shared_strings) else raw_value
    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"
    return raw_value


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.findall(".//main:t", XLSX_NS)) for item in root.findall("main:si", XLSX_NS)]


def _workbook_sheets(workbook_xml: ElementTree.Element, rels_xml: ElementTree.Element) -> list[tuple[str, str]]:
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_xml.findall("rel:Relationship", REL_NS)
        if "Id" in rel.attrib and "Target" in rel.attrib
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook_xml.findall(".//main:sheet", XLSX_NS):
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        if rel_id and rel_id in rel_targets:
            target = rel_targets[rel_id]
            path = str(PurePosixPath("xl") / target) if not target.startswith(("/", "xl/")) else target.lstrip("/")
            sheets.append((sheet.attrib.get("name", "Sheet"), path))
    return sheets


def _dedupe_headers(raw_headers: list[str]) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(raw_headers):
        cleaned = _clean_header(header) or f"column_{index + 1}"
        key = cleaned.casefold()
        seen_count = seen.get(key, 0)
        headers.append(cleaned if seen_count == 0 else f"{cleaned} ({seen_count + 1})")
        seen[key] = seen_count + 1
    return headers


def _target_acos_value(
    raw_value: str | None,
    workspace_defaults: dict[str, Any],
    errors: list[BulkProductRowValidationError],
) -> Decimal | None:
    if raw_value is not None and raw_value.strip():
        return _parse_percentage("target_acos", raw_value, errors)
    default = workspace_defaults.get("target_acos", DEFAULT_TARGET_ACOS)
    return _normalise_percentage_decimal("target_acos", Decimal(str(default)), errors)


def _parse_percentage(
    field: str,
    raw_value: str,
    errors: list[BulkProductRowValidationError],
) -> Decimal | None:
    cleaned = raw_value.strip()
    had_percent = "%" in cleaned
    cleaned = cleaned.replace("%", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        errors.append(_error(field, "Target ACOS must be a number or percentage", raw_value))
        return None
    if had_percent or value > Decimal("1"):
        value = value / Decimal("100")
    return _normalise_percentage_decimal(field, value, errors, raw_value=raw_value)


def _normalise_percentage_decimal(
    field: str,
    value: Decimal,
    errors: list[BulkProductRowValidationError],
    *,
    raw_value: str | None = None,
) -> Decimal | None:
    if value > Decimal("1"):
        value = value / Decimal("100")
    if not (Decimal("0") < value <= Decimal("1")):
        errors.append(_error(field, "Target ACOS must be greater than 0% and no more than 100%", raw_value or str(value)))
        return None
    return value.quantize(Decimal("0.0001"))


def _money_value(
    field: str,
    raw_value: str | None,
    default: Any,
    errors: list[BulkProductRowValidationError],
) -> Decimal | None:
    if raw_value is None or not raw_value.strip():
        value = Decimal(str(default))
    else:
        cleaned = _clean_money(raw_value)
        try:
            value = Decimal(cleaned)
        except InvalidOperation:
            errors.append(_error(field, f"{field} must be a currency amount", raw_value))
            return None

    if value <= Decimal("0"):
        errors.append(_error(field, f"{field} must be greater than 0", raw_value or str(value)))
        return None
    if abs(value.as_tuple().exponent) > 4:
        errors.append(_error(field, f"{field} must have no more than 4 decimal places", raw_value or str(value)))
        return None
    return value.quantize(Decimal("0.0000"))


def _clean_money(value: str) -> str:
    cleaned = value.strip().replace(",", "")
    cleaned = re.sub(r"(?i)\b(USD|CAD|GBP|EUR|SEK|PLN|JPY|AUD|MXN|BRL)\b", "", cleaned)
    cleaned = cleaned.translate(str.maketrans({"$": "", "€": "", "£": "", "¥": ""}))
    return cleaned.strip()


def _optional_text(
    value: str | None,
    *,
    max_length: int,
    field: str,
    errors: list[BulkProductRowValidationError],
) -> str | None:
    if value is None or not value.strip():
        return None
    sanitized = sanitize_preview_value(value.strip())
    if len(sanitized) > max_length:
        errors.append(_error(field, f"{field} must be {max_length} characters or fewer", value))
        return None
    return sanitized


def _normalise_marketplace(value: str) -> str | None:
    key = re.sub(r"[^A-Za-z0-9]+", " ", value).strip().upper()
    return MARKETPLACE_ALIASES.get(key)


def _clean_header(header: str) -> str:
    return re.sub(r"\s+", " ", str(header).replace("\ufeff", "").strip())


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    if sample.count("\t") > sample.count(","):
        return "\t"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        return dialect.delimiter
    except csv.Error:
        return ","


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha()).upper()
    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - ord("A") + 1)
    return max(index - 1, 0)


def _row_number(row_el: ElementTree.Element) -> int:
    raw = row_el.attrib.get("r")
    return int(raw) if raw and raw.isdigit() else 1


def _identity_name_key(product_name: str | None) -> str:
    return re.sub(r"\s+", " ", (product_name or "").strip().casefold())


def _uuid_or_none(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError:
        return None


def _error(field: str, message: str, raw_value: str | None = None) -> BulkProductRowValidationError:
    return BulkProductRowValidationError(
        field=field,
        message=message,
        raw_value=sanitize_preview_value(raw_value.strip()) if isinstance(raw_value, str) and raw_value.strip() else None,
    )
