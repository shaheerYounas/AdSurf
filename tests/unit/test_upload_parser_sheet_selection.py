"""Tests for the _select_best_candidate sheet selection logic.

This validates the fix for Bug 1 where bulk workbook parser was selecting
'Portfolios' instead of 'Sponsored Products Campaigns'.
"""

from apps.api.app.services.upload_parser import _select_best_candidate


def test_selects_sponsored_products_campaigns_over_portfolios() -> None:
    """In a bulk workbook, 'Sponsored Products Campaigns' should be selected before 'Portfolios'."""
    candidates: list[tuple[str, str, int]] = [
        ("Portfolios", "xl/worksheets/sheet1.xml", 12),
        ("Sponsored Products Campaigns", "xl/worksheets/sheet2.xml", 52),
    ]
    selected = _select_best_candidate(candidates)
    assert selected[0] == "Sponsored Products Campaigns"


def test_selects_sp_search_term_report_over_portfolios() -> None:
    """'SP Search Term Report' should be selected before 'Portfolios'."""
    candidates: list[tuple[str, str, int]] = [
        ("Portfolios", "xl/worksheets/sheet1.xml", 12),
        ("SP Search Term Report", "xl/worksheets/sheet7.xml", 27),
    ]
    selected = _select_best_candidate(candidates)
    assert selected[0] == "SP Search Term Report"


def test_selects_first_matching_priority_when_multiple_bulk_sheets() -> None:
    """When multiple sheets match priority, the first in priority list wins."""
    candidates: list[tuple[str, str, int]] = [
        ("Portfolios", "xl/worksheets/sheet1.xml", 12),
        ("SP Search Term Report", "xl/worksheets/sheet7.xml", 27),
        ("Sponsored Products Campaigns", "xl/worksheets/sheet2.xml", 52),
    ]
    selected = _select_best_candidate(candidates)
    # "Sponsored Products Campaigns" is first in BULK_SHEET_PRIORITY_NAMES
    assert selected[0] == "Sponsored Products Campaigns"


def test_falls_back_to_single_candidate() -> None:
    """When only one sheet has data, it should be selected regardless of name."""
    candidates: list[tuple[str, str, int]] = [
        ("Some Unknown Sheet", "xl/worksheets/sheet1.xml", 8),
    ]
    selected = _select_best_candidate(candidates)
    assert selected[0] == "Some Unknown Sheet"


def test_falls_back_to_column_count_when_no_priority_match() -> None:
    """When no sheet matches priority names, select the one with most columns."""
    candidates: list[tuple[str, str, int]] = [
        ("Config", "xl/worksheets/sheet3.xml", 10),
        ("Sheet10", "xl/worksheets/sheet10.xml", 2),
        ("Sponsored Brands Campaigns", "xl/worksheets/sheet4.xml", 51),
    ]
    selected = _select_best_candidate(candidates)
    # "Sponsored Brands Campaigns" has 51 columns, most of the three
    assert selected[0] == "Sponsored Brands Campaigns"


def test_finds_sponsored_products_search_term_partial_match() -> None:
    """'Sponsored_Products_Search_term_' (truncated) should match keyword 'sponsored products search term'."""
    candidates: list[tuple[str, str, int]] = [
        ("Sponsored_Products_Search_term_", "xl/worksheets/sheet1.xml", 26),
        ("Sheet10", "xl/worksheets/sheet10.xml", 2),
    ]
    selected = _select_best_candidate(candidates)
    # "sponsored products search term" is in _SINGLE_SHEET_PRIORITY_NAMES
    assert "search" in selected[0].lower()