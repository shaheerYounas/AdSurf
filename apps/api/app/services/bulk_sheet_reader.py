"""Parse Amazon Sponsored Products Bulk Operation XLSX files.

Amazon exports bulk sheets in two formats:
  - Legacy  : single sheet, each row has an "Entity" column
               (Campaign / Ad Group / Keyword / Product Ad / Bidding Adjustment)
  - Modern  : single sheet, each row has a "Record Type" column with full names
               e.g. "Sponsored Products Campaign", "Sponsored Products Keyword"
               Informational-only performance columns carry the suffix " (Informational only)"

Both formats are handled transparently.  The reader produces a `BulkSheetSnapshot`
containing flat lists of campaigns, ad groups, keywords, targets, and product ads —
the full current state of the account at the time the file was exported.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree


# ---------------------------------------------------------------------------
# Output data model
# ---------------------------------------------------------------------------

@dataclass
class BulkCampaign:
    campaign_id: str
    name: str
    status: str          # enabled / paused / archived
    daily_budget: Decimal | None
    targeting_type: str | None   # manual / auto
    start_date: str | None
    end_date: str | None
    bidding_strategy: str | None


@dataclass
class BulkAdGroup:
    ad_group_id: str
    campaign_id: str
    campaign_name: str
    name: str
    status: str
    default_bid: Decimal | None


@dataclass
class BulkKeyword:
    keyword_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    keyword_text: str
    match_type: str       # exact / phrase / broad
    bid: Decimal | None
    status: str


@dataclass
class BulkTarget:
    target_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    expression: str       # ASIN targeting expression or auto target group
    bid: Decimal | None
    status: str


@dataclass
class BulkNegativeKeyword:
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    keyword_text: str
    match_type: str       # negative exact / negative phrase


@dataclass
class BulkProductAd:
    ad_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    asin: str | None
    sku: str | None
    status: str


@dataclass
class BulkSheetSnapshot:
    filename: str
    date_range_start: str | None   # from filename or sheet metadata
    date_range_end: str | None
    account_id: str | None         # from filename pattern
    campaigns: list[BulkCampaign] = field(default_factory=list)
    ad_groups: list[BulkAdGroup] = field(default_factory=list)
    keywords: list[BulkKeyword] = field(default_factory=list)
    targets: list[BulkTarget] = field(default_factory=list)
    negative_keywords: list[BulkNegativeKeyword] = field(default_factory=list)
    product_ads: list[BulkProductAd] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_campaigns(self) -> int:
        return len(self.campaigns)

    @property
    def active_campaigns(self) -> int:
        return sum(1 for c in self.campaigns if c.status.lower() == "enabled")

    @property
    def total_keywords(self) -> int:
        return len(self.keywords)

    @property
    def total_targets(self) -> int:
        return len(self.targets)

    @property
    def total_product_ads(self) -> int:
        return len(self.product_ads)


# ---------------------------------------------------------------------------
# Filename parser
# ---------------------------------------------------------------------------

_BULK_FILENAME_RE = re.compile(
    r"bulk-([a-z0-9]+)-(\d{8})-(\d{8})-\d+",
    re.IGNORECASE,
)


def _parse_bulk_filename(filename: str) -> tuple[str | None, str | None, str | None]:
    """Return (account_id, start_date, end_date) from the bulk filename."""
    m = _BULK_FILENAME_RE.search(filename)
    if not m:
        return None, None, None
    account_id = m.group(1)
    start_raw, end_raw = m.group(2), m.group(3)
    def _fmt(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return account_id, _fmt(start_raw), _fmt(end_raw)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_bulk_sheet(content: bytes, filename: str) -> BulkSheetSnapshot:
    account_id, start_date, end_date = _parse_bulk_filename(filename)
    snapshot = BulkSheetSnapshot(
        filename=filename,
        date_range_start=start_date,
        date_range_end=end_date,
        account_id=account_id,
    )

    lower = filename.lower()
    if lower.endswith(".xlsx"):
        _parse_xlsx(content, snapshot)
    elif lower.endswith(".csv"):
        _parse_csv(content, snapshot)
    else:
        snapshot.warnings.append(f"Unsupported file extension for bulk sheet: {filename}")

    return snapshot


# ---------------------------------------------------------------------------
# XLSX parser
# ---------------------------------------------------------------------------

XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}

_BULK_SHEET_NAMES = {
    "sponsored products",
    "sp campaigns",
    "sp ad groups",
    "sp keywords",
    "sponsored products campaigns",
    "sponsored products ad groups",
    "sponsored products keywords",
    "sponsored products product ads",
    "sponsored products targets",
    "sponsored products negative keywords",
    "sponsored products campaign negative keywords",
    "sponsored products ad group negative keywords",
}


def _parse_xlsx(content: bytes, snapshot: BulkSheetSnapshot) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            shared_strings = _read_shared_strings(zf)
            workbook_xml = ElementTree.fromstring(zf.read("xl/workbook.xml"))
            rels_xml = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            sheets = _workbook_sheets(workbook_xml, rels_xml)

            for sheet_name, sheet_path in sheets:
                rows = _read_sheet_rows(zf, sheet_path, shared_strings)
                if not rows:
                    continue
                sname = sheet_name.lower().strip()
                if sname in _BULK_SHEET_NAMES or _looks_like_bulk_sheet(rows[0] if rows else {}):
                    _process_rows(rows, snapshot, sheet_name)
    except (zipfile.BadZipFile, KeyError) as exc:
        snapshot.warnings.append(f"Could not open XLSX: {exc}")


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        xml = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
        return [
            "".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
            for si in xml.findall("main:si", XLSX_NS)
        ]
    except KeyError:
        return []


def _workbook_sheets(wb_xml: ElementTree.Element, rels_xml: ElementTree.Element) -> list[tuple[str, str]]:
    rels: dict[str, str] = {}
    for rel in rels_xml.findall("rel:Relationship", REL_NS):
        rels[rel.get("Id", "")] = rel.get("Target", "")
    sheets: list[tuple[str, str]] = []
    for sheet in wb_xml.findall(".//main:sheet", XLSX_NS):
        rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rels.get(rid, "")
        if target:
            # Targets can be absolute ("/xl/worksheets/sheet1.xml") or relative ("worksheets/sheet1.xml")
            t = target.lstrip("/")
            path = t if t.startswith("xl/") else f"xl/{t}"
            sheets.append((sheet.get("name", ""), path))
    return sheets


def _read_sheet_rows(zf: zipfile.ZipFile, path: str, shared_strings: list[str]) -> list[dict[str, str]]:
    try:
        xml = ElementTree.fromstring(zf.read(path))
    except (KeyError, ElementTree.ParseError):
        return []

    row_els = xml.findall(".//main:row", XLSX_NS)
    if not row_els:
        return []

    headers: list[str] = []
    data_rows: list[dict[str, str]] = []

    for i, row_el in enumerate(row_els):
        cells: list[str] = []
        for cell in row_el.findall("main:c", XLSX_NS):
            col_idx = _col_index(cell.get("r", ""))
            while len(cells) < col_idx:
                cells.append("")
            t_attr = cell.get("t", "")

            # inlineStr: <c t="inlineStr"><is><t>value</t></is></c>  (openpyxl default)
            if t_attr == "inlineStr":
                parts = cell.findall(".//main:t", XLSX_NS)
                cells.append("".join(p.text or "" for p in parts))
                continue

            val_el = cell.find("main:v", XLSX_NS)
            raw = val_el.text if val_el is not None else None
            if raw is None:
                cells.append("")
                continue
            if t_attr == "s":
                try:
                    cells.append(shared_strings[int(raw)])
                except (IndexError, ValueError):
                    cells.append(raw)
            elif t_attr == "str":
                inline = cell.find("main:is/main:t", XLSX_NS)
                cells.append(inline.text if inline is not None else raw)
            else:
                cells.append(raw)

        if i == 0:
            headers = [_norm(c) for c in cells]
        else:
            if all(c == "" for c in cells):
                continue
            row: dict[str, str] = {}
            for j, h in enumerate(headers):
                row[h] = cells[j].strip() if j < len(cells) else ""
            data_rows.append(row)

    return data_rows


def _col_index(ref: str) -> int:
    """Convert Excel column ref like 'A', 'B', 'AA' to 0-based index."""
    letters = re.sub(r"\d", "", ref).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def _parse_csv(content: bytes, snapshot: BulkSheetSnapshot) -> None:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [
        {_norm(k): (v or "").strip() for k, v in row.items()}
        for row in reader
        if any(v for v in row.values())
    ]
    if rows:
        _process_rows(rows, snapshot, "CSV")


# ---------------------------------------------------------------------------
# Row dispatcher — handles both legacy (Entity) and modern (Record Type) formats
# ---------------------------------------------------------------------------

_ENTITY_CAMPAIGN    = {"campaign", "sponsored products campaign"}
_ENTITY_AD_GROUP    = {"ad group", "sponsored products ad group"}
_ENTITY_KEYWORD     = {"keyword", "sponsored products keyword"}
_ENTITY_TARGET      = {"product targeting", "sponsored products target", "target"}
_ENTITY_NEG_KW      = {"negative keyword", "campaign negative keyword",
                       "sponsored products campaign negative keyword",
                       "sponsored products ad group negative keyword",
                       "ad group negative keyword"}
_ENTITY_PRODUCT_AD  = {"product ad", "sponsored products product ad", "ad"}


def _process_rows(rows: list[dict[str, str]], snapshot: BulkSheetSnapshot, sheet_name: str) -> None:
    if not rows:
        return

    # Determine whether this sheet has an entity discriminator column
    sample = rows[0]
    entity_col = _find_col(sample, {"entity", "record type"})

    for row in rows:
        entity_val = (row.get(entity_col, "") if entity_col else "").lower().strip()

        # If no entity column, infer from which columns are populated
        if not entity_col:
            entity_val = _infer_entity(row)

        if entity_val in _ENTITY_CAMPAIGN:
            c = _parse_campaign(row)
            if c:
                snapshot.campaigns.append(c)
        elif entity_val in _ENTITY_AD_GROUP:
            ag = _parse_ad_group(row)
            if ag:
                snapshot.ad_groups.append(ag)
        elif entity_val in _ENTITY_KEYWORD:
            kw = _parse_keyword(row)
            if kw:
                snapshot.keywords.append(kw)
        elif entity_val in _ENTITY_TARGET:
            tgt = _parse_target(row)
            if tgt:
                snapshot.targets.append(tgt)
        elif entity_val in _ENTITY_NEG_KW:
            neg = _parse_negative_keyword(row)
            if neg:
                snapshot.negative_keywords.append(neg)
        elif entity_val in _ENTITY_PRODUCT_AD:
            ad = _parse_product_ad(row)
            if ad:
                snapshot.product_ads.append(ad)


def _infer_entity(row: dict[str, str]) -> str:
    """Infer entity type from populated columns when no discriminator column exists."""
    if _get(row, {"keyword text", "keyword"}) and not _get(row, {"targeting expression", "expression"}):
        return "keyword"
    if _get(row, {"targeting expression", "expression", "product targeting expression"}):
        return "product targeting"
    if _get(row, {"ad group name"}) and not _get(row, {"campaign daily budget", "daily budget"}):
        return "ad group"
    if _get(row, {"campaign name"}) and _get(row, {"campaign daily budget", "daily budget", "budget"}):
        return "campaign"
    return ""


# ---------------------------------------------------------------------------
# Per-entity parsers
# ---------------------------------------------------------------------------

def _parse_campaign(row: dict[str, str]) -> BulkCampaign | None:
    name = _get(row, {"campaign name", "campaign"})
    if not name:
        return None
    return BulkCampaign(
        campaign_id=_get(row, {"campaign id"}) or "",
        name=name,
        status=_get(row, {"campaign status", "status"}) or "unknown",
        daily_budget=_decimal(row, {"campaign daily budget", "daily budget", "budget"}),
        targeting_type=_get(row, {"targeting type", "campaign targeting type"}),
        start_date=_get(row, {"campaign start date", "start date"}),
        end_date=_get(row, {"campaign end date", "end date"}),
        bidding_strategy=_get(row, {"bidding strategy", "bid strategy"}),
    )


def _parse_ad_group(row: dict[str, str]) -> BulkAdGroup | None:
    name = _get(row, {"ad group name"})
    if not name:
        return None
    return BulkAdGroup(
        ad_group_id=_get(row, {"ad group id"}) or "",
        campaign_id=_get(row, {"campaign id"}) or "",
        campaign_name=_get(row, {"campaign name", "campaign"}) or "",
        name=name,
        status=_get(row, {"ad group status", "status"}) or "unknown",
        default_bid=_decimal(row, {"ad group default bid", "default bid", "max bid"}),
    )


def _parse_keyword(row: dict[str, str]) -> BulkKeyword | None:
    kw_text = _get(row, {"keyword text", "keyword"})
    if not kw_text:
        return None
    return BulkKeyword(
        keyword_id=_get(row, {"keyword id"}) or "",
        campaign_id=_get(row, {"campaign id"}) or "",
        campaign_name=_get(row, {"campaign name", "campaign"}) or "",
        ad_group_id=_get(row, {"ad group id"}) or "",
        ad_group_name=_get(row, {"ad group name"}) or "",
        keyword_text=kw_text,
        match_type=(_get(row, {"match type", "keyword match type"}) or "").lower(),
        bid=_decimal(row, {"keyword bid", "bid"}),
        status=_get(row, {"keyword status", "status"}) or "unknown",
    )


def _parse_target(row: dict[str, str]) -> BulkTarget | None:
    expr = _get(row, {"product targeting expression", "targeting expression", "expression"})
    if not expr:
        return None
    return BulkTarget(
        target_id=_get(row, {"target id"}) or "",
        campaign_id=_get(row, {"campaign id"}) or "",
        campaign_name=_get(row, {"campaign name", "campaign"}) or "",
        ad_group_id=_get(row, {"ad group id"}) or "",
        ad_group_name=_get(row, {"ad group name"}) or "",
        expression=expr,
        bid=_decimal(row, {"target bid", "bid"}),
        status=_get(row, {"target status", "status"}) or "unknown",
    )


def _parse_negative_keyword(row: dict[str, str]) -> BulkNegativeKeyword | None:
    kw_text = _get(row, {"keyword text", "keyword"})
    if not kw_text:
        return None
    return BulkNegativeKeyword(
        campaign_id=_get(row, {"campaign id"}) or "",
        campaign_name=_get(row, {"campaign name", "campaign"}) or "",
        ad_group_id=_get(row, {"ad group id"}) or "",
        ad_group_name=_get(row, {"ad group name"}) or "",
        keyword_text=kw_text,
        match_type=(_get(row, {"match type", "keyword match type"}) or "").lower(),
    )


def _parse_product_ad(row: dict[str, str]) -> BulkProductAd | None:
    asin = _get(row, {"asin", "advertised asin"})
    sku = _get(row, {"sku", "advertised sku"})
    if not asin and not sku:
        return None
    return BulkProductAd(
        ad_id=_get(row, {"ad id"}) or "",
        campaign_id=_get(row, {"campaign id"}) or "",
        campaign_name=_get(row, {"campaign name", "campaign"}) or "",
        ad_group_id=_get(row, {"ad group id"}) or "",
        ad_group_name=_get(row, {"ad group name"}) or "",
        asin=asin,
        sku=sku,
        status=_get(row, {"ad status", "status"}) or "unknown",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(value: str) -> str:
    """Normalise a column header: lowercase, collapse non-alphanumeric, strip."""
    cleaned = re.sub(r"\s*\(informational only\)\s*$", "", value.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", " ", cleaned.lower()).strip()


def _find_col(row: dict[str, str], candidates: set[str]) -> str | None:
    for key in row:
        if _norm(key) in candidates:
            return key
    return None


def _get(row: dict[str, str], names: set[str]) -> str:
    for name in names:
        v = row.get(name, "").strip()
        if v:
            return v
    return ""


def _decimal(row: dict[str, str], names: set[str]) -> Decimal | None:
    raw = _get(row, names).replace(",", "").replace("$", "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw).quantize(Decimal("0.0001"))
    except InvalidOperation:
        return None


def _looks_like_bulk_sheet(sample_row: dict[str, str]) -> bool:
    keys = {k.lower() for k in sample_row}
    required = {"campaign id", "campaign name"}
    return required.issubset(keys) and any(
        k in keys for k in {"entity", "record type", "keyword text", "keyword", "ad group name"}
    )
