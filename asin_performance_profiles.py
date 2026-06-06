"""
Extract advertised ASINs from an SP Search Term Report and build
per-ASIN performance profiles.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Matches a 10-char B0... ASIN not immediately surrounded by other alphanum chars.
# Lookbehind/lookahead avoids false matches when ASINs are glued to underscores.
ASIN_RE = re.compile(r"(?i)(?<![A-Z0-9])(B[A-Z0-9]{9})(?![A-Z0-9])")

# Matches Amazon Parent/Product-Group IDs (APR + 9 alphanum chars).
PARENT_RE = re.compile(r"(?i)(?<![A-Z0-9])(APR[A-Z0-9]{9})(?![A-Z0-9])")

REQUIRED_COLUMNS = {
    "Campaign Name",
    "Customer Search Term",
    "Impressions",
    "Clicks",
    "Spend",
    "7 Day Total Sales ",       # trailing space is intentional – matches Amazon export
    "7 Day Total Orders (#)",
}

# Columns searched for a child ASIN, in priority order
ASIN_SOURCE_COLS = ["Campaign Name", "Ad Group Name", "Portfolio name"]

OUTPUT_FILE = "ASIN_Performance_Profiles.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_asin(text: str) -> str:
    """Return the first B0… ASIN found in *text* (case-insensitive), or ''."""
    if not isinstance(text, str):
        return ""
    m = ASIN_RE.search(text)
    return m.group(1).upper() if m else ""


def _find_parent(text: str) -> str:
    """Return 'ParentGroup_<ID>' if an APR… parent ID is found, else ''."""
    if not isinstance(text, str):
        return ""
    m = PARENT_RE.search(text)
    return f"ParentGroup_{m.group(1).upper()}" if m else ""


def load_report(path: str | Path) -> pd.DataFrame:
    """Load a CSV or XLSX SP Search Term Report into a DataFrame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")

    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    else:
        # Try UTF-8-BOM first (Amazon's default), fall back to latin-1
        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path, dtype=str, encoding="latin-1")

    # Strip leading/trailing whitespace from column names
    df.columns = [c.strip() for c in df.columns]
    # Re-apply the trailing-space column name Amazon uses for Sales
    sales_col_candidates = [c for c in df.columns if c.strip() == "7 Day Total Sales"]
    if sales_col_candidates and "7 Day Total Sales " not in df.columns:
        df.rename(columns={sales_col_candidates[0]: "7 Day Total Sales "}, inplace=True)

    return df


def validate_columns(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Report is missing required columns: {sorted(missing)}")


def extract_asins(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'Extracted_Advertised_ASIN' to *df*.

    Priority:
      1. Child ASIN (B0…) from Campaign Name → Ad Group Name → Portfolio name
      2. Parent Group ID (APR…) from Campaign Name → labelled ParentGroup_<ID>
      3. "Unknown_Entity" if nothing found
    """
    df = df.copy()
    result = pd.Series("", index=df.index)

    # Step 1 – child ASIN search across source columns in order
    for col in ASIN_SOURCE_COLS:
        if col not in df.columns:
            continue
        unfilled = result == ""
        if not unfilled.any():
            break
        result[unfilled] = df.loc[unfilled, col].apply(_find_asin)

    # Step 2 – parent group fallback (Campaign Name only) for still-empty rows
    unfilled = result == ""
    if unfilled.any():
        result[unfilled] = df.loc[unfilled, "Campaign Name"].apply(_find_parent)

    # Step 3 – final fallback
    result = result.replace("", "Unknown_Entity")

    df["Extracted_Advertised_ASIN"] = result
    return df


def _to_numeric(series: pd.Series) -> pd.Series:
    """Coerce a string series to float, stripping currency symbols and commas."""
    return (
        series.astype(str)
        .str.replace(r"[,$£€¥₹₩%]", "", regex=True)
        .str.strip()
        .replace("", "0")
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
    )


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Group by ASIN and compute the performance profile."""
    numeric_cols = ["Impressions", "Clicks", "Spend", "7 Day Total Sales ", "7 Day Total Orders (#)"]
    for col in numeric_cols:
        df[col] = _to_numeric(df[col])

    grouped = df.groupby("Extracted_Advertised_ASIN", sort=False).agg(
        Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"),
        Spend=("Spend", "sum"),
        Sales=("7 Day Total Sales ", "sum"),
        Orders=("7 Day Total Orders (#)", "sum"),
        Unique_Search_Terms=("Customer Search Term", "nunique"),
    ).reset_index()

    # Calculated fields
    grouped["CPC"] = (grouped["Spend"] / grouped["Clicks"].replace(0, pd.NA)).fillna(0).round(4)
    grouped["ACOS"] = (grouped["Spend"] / grouped["Sales"].replace(0, pd.NA)).fillna(0).round(4)
    grouped["Conversion_Rate"] = (grouped["Orders"] / grouped["Clicks"].replace(0, pd.NA)).fillna(0).round(4)

    return grouped.sort_values("Spend", ascending=False).reset_index(drop=True)


def print_summary(profiles: pd.DataFrame) -> None:
    real_asins = profiles[profiles["Extracted_Advertised_ASIN"] != "Unknown_ASIN"]
    print("\n--- SP Search Term Report - ASIN Performance Summary ---")
    print(f"  Total ASINs found : {len(real_asins):,}")
    if len(real_asins) < len(profiles):
        print(f"  Rows with no ASIN : {len(profiles) - len(real_asins):,}  (labelled Unknown_ASIN)")
    print(f"  Total Spend       : ${profiles['Spend'].sum():,.2f}")
    print(f"  Total Sales       : ${profiles['Sales'].sum():,.2f}")
    print(f"  Total Orders      : {int(profiles['Orders'].sum()):,}")
    print(f"  Output saved to   : {OUTPUT_FILE}")
    print("-" * 56 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(report_path: str | Path) -> pd.DataFrame:
    df = load_report(report_path)
    validate_columns(df)
    df = extract_asins(df)
    profiles = aggregate(df)
    profiles.to_csv(OUTPUT_FILE, index=False)
    print_summary(profiles)
    return profiles


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python asin_performance_profiles.py <path_to_report.csv|xlsx>")
        sys.exit(1)
    main(sys.argv[1])
