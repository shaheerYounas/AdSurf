import io
import zipfile
from decimal import Decimal

import pytest

from apps.api.app.schemas.bulk_product_import import BulkImportConflictStrategy, BulkImportRowStatus
from apps.api.app.services.bulk_product_import_service import (
    BulkProductImportParseError,
    BulkProductImportService,
    canonical_field_for_header,
    parse_file_to_rows,
)


def test_common_header_variations_are_detected() -> None:
    assert canonical_field_for_header(" Product Title ") == "product_name"
    assert canonical_field_for_header("advertised product asin") == "asin"
    assert canonical_field_for_header("Merchant SKU") == "sku"
    assert canonical_field_for_header("REGION") == "marketplace"
    assert canonical_field_for_header("target acoS %") == "target_acos"
    assert canonical_field_for_header("campaign budget") == "default_budget"
    assert canonical_field_for_header("keyword bid") == "default_bid"


def test_csv_parser_preserves_source_row_numbers_and_duplicate_headers() -> None:
    content = (
        "\ufeffProduct Name,Product Name,ASIN,SKU\n"
        '"Garlic Press, Stainless",Ignored duplicate,b0abc12345,SKU-1\n'
        ",,,\n"
        "Silicone Spatula,Duplicate title,B0ABC12346,SKU-2\n"
    ).encode("utf-8")

    rows, mapping = parse_file_to_rows(content, "products.csv")

    assert mapping["Product Name"] == "product_name"
    assert mapping["Product Name (2)"] == "product_name"
    assert [row.row_number for row in rows] == [2, 4]
    assert rows[0].raw_row["Product Name"] == "Garlic Press, Stainless"
    assert rows[0].raw_row["Product Name (2)"] == "Ignored duplicate"


def test_xlsx_parser_selects_product_sheet_and_skips_hidden_rows() -> None:
    rows, mapping = parse_file_to_rows(
        _minimal_xlsx(
            data_sheet_xml="""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Product Name</t></is></c>
                  <c r="B1" t="inlineStr"><is><t>ASIN</t></is></c>
                  <c r="C1" t="inlineStr"><is><t>Target ACOS</t></is></c>
                </row>
                <row r="2">
                  <c r="A2" t="inlineStr"><is><t>Visible Product</t></is></c>
                  <c r="B2" t="inlineStr"><is><t>b0abc12345</t></is></c>
                  <c r="C2"><v>30</v></c>
                </row>
                <row r="3" hidden="1">
                  <c r="A3" t="inlineStr"><is><t>Hidden Product</t></is></c>
                  <c r="B3" t="inlineStr"><is><t>B0ABC12346</t></is></c>
                  <c r="C3"><v>30</v></c>
                </row>
                <row r="4">
                  <c r="A4" t="inlineStr"><is><t>Second Visible</t></is></c>
                  <c r="B4" t="inlineStr"><is><t>B0ABC12347</t></is></c>
                  <c r="C4"><f>SUM(10,20)</f><v>30</v></c>
                </row>
              </sheetData>
            </worksheet>""",
        ),
        "products.xlsx",
    )

    assert mapping["Product Name"] == "product_name"
    assert [row.row_number for row in rows] == [2, 4]
    assert rows[1].raw_row["Target ACOS"] == "=SUM(10,20)"


@pytest.mark.parametrize(
    ("raw_acos", "expected"),
    [
        ("30", Decimal("0.3000")),
        ("30%", Decimal("0.3000")),
        ("0.30", Decimal("0.3000")),
        ("0.3", Decimal("0.3000")),
    ],
)
def test_target_acos_parses_common_percent_formats(raw_acos: str, expected: Decimal) -> None:
    row = _parse_one(f"Product Name,ASIN,Target ACOS\nWidget,b0abc12345,{raw_acos}\n")

    assert row.status == BulkImportRowStatus.VALID
    assert row.asin == "B0ABC12345"
    assert row.target_acos == expected


def test_default_target_acos_only_applies_when_file_value_is_missing() -> None:
    service = BulkProductImportService()

    missing_rows, _, _ = service.parse_and_validate(
        content=b"Product Name,ASIN\nWidget,B0ABC12345\n",
        filename="products.csv",
        workspace_defaults={"target_acos": Decimal("0.2500")},
    )
    present_rows, _, _ = service.parse_and_validate(
        content=b"Product Name,ASIN,Target ACOS\nWidget,B0ABC12345,40\n",
        filename="products.csv",
        workspace_defaults={"target_acos": Decimal("0.2500")},
    )

    assert missing_rows[0].target_acos == Decimal("0.2500")
    assert present_rows[0].target_acos == Decimal("0.4000")


def test_money_fields_accept_currency_text_and_reject_bad_values() -> None:
    row = _parse_one("Product Name,ASIN,Target ACOS,Default Budget,Default Bid\nWidget,B0ABC12345,30,USD 50,$1.25\n")
    bad = _parse_one("Product Name,ASIN,Target ACOS,Default Budget,Default Bid\nWidget,B0ABC12345,30,-5,1.12345\n")

    assert row.default_budget == Decimal("50.0000")
    assert row.default_bid == Decimal("1.2500")
    assert bad.status == BulkImportRowStatus.INVALID
    assert {error.field for error in bad.validation_errors} == {"default_budget", "default_bid"}


def test_marketplace_currency_and_identifier_validation() -> None:
    wrong_currency = _parse_one("Product Name,ASIN,Target ACOS,Marketplace,Currency\nWidget,B0ABC12345,30,US,EUR\n")
    no_identifier = _parse_one("Product Name,Target ACOS\nWidget,30\n")

    assert wrong_currency.status == BulkImportRowStatus.INVALID
    assert wrong_currency.validation_errors[0].field == "currency"
    assert no_identifier.status == BulkImportRowStatus.INVALID
    assert any(error.field == "asin" for error in no_identifier.validation_errors)


def test_duplicate_detection_marks_asin_sku_and_name_collisions() -> None:
    service = BulkProductImportService()
    rows, _, _ = service.parse_and_validate(
        content=(
            b"Product Name,ASIN,SKU,Target ACOS\n"
            b"Widget A,B0ABC12345,SKU-1,30\n"
            b"Widget B,B0ABC12345,SKU-2,30\n"
            b"Widget C,B0ABC12346,SKU-2,30\n"
            b"Widget A,B0ABC12347,SKU-3,30\n"
        ),
        filename="products.csv",
        workspace_defaults={},
    )

    assert [row.status for row in rows] == [
        BulkImportRowStatus.VALID,
        BulkImportRowStatus.DUPLICATE_IN_FILE,
        BulkImportRowStatus.DUPLICATE_IN_FILE,
        BulkImportRowStatus.DUPLICATE_IN_FILE,
    ]


def test_workspace_conflicts_follow_selected_policy() -> None:
    service = BulkProductImportService()
    rows, _, _ = service.parse_and_validate(
        content=b"Product Name,ASIN,SKU,Target ACOS\nWidget,B0ABC12345,SKU-1,30\n",
        filename="products.csv",
        workspace_defaults={},
    )

    skipped = service.check_workspace_conflicts(
        rows=rows,
        existing_by_asin={"B0ABC12345": "00000000-0000-0000-0000-000000000101"},
        existing_by_sku={},
        conflict_strategy=BulkImportConflictStrategy.SKIP_EXISTING,
    )
    updating = service.check_workspace_conflicts(
        rows=rows,
        existing_by_asin={"B0ABC12345": "00000000-0000-0000-0000-000000000101"},
        existing_by_sku={},
        conflict_strategy=BulkImportConflictStrategy.UPDATE_EXISTING,
    )

    assert skipped[0].status == BulkImportRowStatus.ALREADY_EXISTS
    assert str(updating[0].product_id) == "00000000-0000-0000-0000-000000000101"
    assert updating[0].status == BulkImportRowStatus.VALID


def test_parser_accepts_more_than_500_rows_and_rejects_malformed_csv_and_blank_xlsx() -> None:
    many_rows = "Product Name,ASIN,Target ACOS\n" + "".join(f"Widget {index},B0ABC{index:05d},30\n" for index in range(501))

    rows, mapping = parse_file_to_rows(many_rows.encode("utf-8"), "products.csv")
    with pytest.raises(BulkProductImportParseError) as malformed:
        parse_file_to_rows(b'Product Name,ASIN\n"Bad row,B0ABC12345\n', "products.csv")
    with pytest.raises(BulkProductImportParseError) as blank:
        parse_file_to_rows(_minimal_xlsx(data_sheet_xml="<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData/></worksheet>"), "blank.xlsx")

    assert len(rows) == 501
    assert mapping["Product Name"] == "product_name"
    assert rows[-1].row_number == 502
    assert malformed.value.code == "MALFORMED_CSV"
    assert blank.value.code == "EMPTY_WORKBOOK"


def test_formula_like_values_are_sanitized_for_preview_and_creation() -> None:
    row = _parse_one("Product Name,ASIN,Target ACOS\n=HYPERLINK(\"http://evil.test\"),B0ABC12345,30\n")

    assert row.product_name.startswith("'=")
    assert row.raw_row_json["Product Name"].startswith("'=")


def _parse_one(csv_text: str):
    service = BulkProductImportService()
    rows, _, _ = service.parse_and_validate(content=csv_text.encode("utf-8"), filename="products.csv", workspace_defaults={})
    assert len(rows) == 1
    return rows[0]


def _minimal_xlsx(*, data_sheet_xml: str | None = None) -> bytes:
    if data_sheet_xml is None:
        data_sheet_xml = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>
            <row r="1">
              <c r="A1" t="inlineStr"><is><t>Product Name</t></is></c>
              <c r="B1" t="inlineStr"><is><t>ASIN</t></is></c>
              <c r="C1" t="inlineStr"><is><t>Target ACOS</t></is></c>
            </row>
            <row r="2">
              <c r="A2" t="inlineStr"><is><t>Widget</t></is></c>
              <c r="B2" t="inlineStr"><is><t>B0ABC12345</t></is></c>
              <c r="C2"><v>30</v></c>
            </row>
          </sheetData>
        </worksheet>"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets>
                <sheet name="Readme" sheetId="1" r:id="rId1"/>
                <sheet name="Products" sheetId="2" r:id="rId2"/>
              </sheets>
            </workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
              <Relationship Id="rId2" Type="worksheet" Target="worksheets/sheet2.xml"/>
            </Relationships>""",
        )
        archive.writestr("xl/worksheets/sheet1.xml", "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData/></worksheet>")
        archive.writestr("xl/worksheets/sheet2.xml", data_sheet_xml)
    return output.getvalue()
