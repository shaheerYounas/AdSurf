"""
AmazonDataParser — extracts the Advertised ASIN (your inventory) from an
Amazon Sponsored Products Search Term Report DataFrame.

Strict separation between:
  - Advertised ASINs  (your products) → extracted from naming columns only
  - Targeted  ASINs   (competitors)   → live in Targeting / Customer Search Term
                                        and are NEVER used here
"""

from __future__ import annotations

import re
from typing import Final

import pandas as pd


# ---------------------------------------------------------------------------
# Module-level compiled patterns (compiled once, reused across all calls)
# ---------------------------------------------------------------------------

# 10-char B0… ASIN with negative lookaround so underscores don't create false
# boundaries (unlike \b which treats underscores as word characters).
_ASIN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<![A-Z0-9])(B[A-Z0-9]{9})(?![A-Z0-9])"
)

# 12-char Parent/Product-Group ID: "APR" + 9 alphanum chars.
_PARENT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<![A-Z0-9])(APR[A-Z0-9]{9})(?![A-Z0-9])"
)

# Columns searched for a child ASIN, in strict priority order.
# The Targeting and Customer Search Term columns are intentionally absent.
_ASIN_SOURCE_COLS: Final[tuple[str, ...]] = (
    "Campaign Name",
    "Ad Group Name",
    "Portfolio name",
)

_PARENT_SOURCE_COL: Final[str] = "Campaign Name"
_PARENT_PREFIX: Final[str] = "ParentGroup_"
_DEFAULT_LABEL: Final[str] = "Unknown_Entity"
_OUTPUT_COL: Final[str] = "Extracted_Advertised_ASIN"


# ---------------------------------------------------------------------------
# AmazonDataParser
# ---------------------------------------------------------------------------


class AmazonDataParser:
    """
    Parse an Amazon Sponsored Products Search Term Report DataFrame and
    extract the Advertised ASIN (your inventory) for every row.

    Extraction hierarchy (strict — Targeting/Search Term columns are never read):

      Step 1 – Child ASIN  : scan Campaign Name → Ad Group Name → Portfolio name
                             for a B[A-Z0-9]{9} ASIN token.
      Step 2 – Parent Group: if no child ASIN found, scan Campaign Name for an
                             APR[A-Z0-9]{9} parent ID and prefix it with
                             "ParentGroup_".
      Step 3 – Default     : label remaining rows "Unknown_Entity".

    Parameters
    ----------
    df : pd.DataFrame
        Raw SP Search Term Report, already loaded (CSV or XLSX).  Column names
        must match Amazon's export headers (trailing spaces included where
        Amazon adds them, e.g. "7 Day Total Sales ").

    Raises
    ------
    TypeError
        If *df* is not a pandas DataFrame.
    ValueError
        If the required "Campaign Name" column is absent.

    Examples
    --------
    >>> parser = AmazonDataParser(df)
    >>> enriched = parser.extract_advertised_entities()
    >>> enriched["Extracted_Advertised_ASIN"].value_counts()
    """

    def __init__(self, df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected a pandas DataFrame, got {type(df).__name__!r}.")
        if "Campaign Name" not in df.columns:
            raise ValueError(
                "'Campaign Name' column is required but was not found. "
                "Verify the report was exported from Amazon Ads and column "
                "names have not been renamed."
            )
        self._df = df

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_advertised_entities(self) -> pd.DataFrame:
        """
        Return a copy of the input DataFrame with a new column
        ``Extracted_Advertised_ASIN`` populated according to the strict
        extraction hierarchy described in the class docstring.

        Returns
        -------
        pd.DataFrame
            Same shape as input with one additional column.
        """
        df = self._df.copy()
        df[_OUTPUT_COL] = self._build_entity_series(df)
        return df

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_from(df: pd.DataFrame, col: str, pattern: re.Pattern[str]) -> pd.Series:
        """
        Vectorised extraction of the first capture group of *pattern* from
        column *col*.  Returns a Series of NaN where the column is absent,
        blank, or has no match.  All matches are upper-cased for consistency.
        """
        if col not in df.columns:
            return pd.Series(pd.NA, index=df.index, dtype="object")

        return (
            df[col]
            .astype(str)                          # coerce NaN / float cells to str
            .str.extract(pattern, expand=False)   # NaN on no-match
            .str.upper()                          # normalise case
        )

    @classmethod
    def _step1_child_asin(cls, df: pd.DataFrame) -> pd.Series:
        """
        Step 1: scan naming columns in priority order for a B0… child ASIN.
        Returns a Series where unresolved rows are NaN.
        """
        result: pd.Series = pd.Series(pd.NA, index=df.index, dtype="object")

        for col in _ASIN_SOURCE_COLS:
            unresolved = result.isna()
            if not unresolved.any():
                break                             # all rows resolved — short-circuit
            extracted = cls._extract_from(df, col, _ASIN_RE)
            result = result.fillna(extracted)

        return result

    @classmethod
    def _step2_parent_group(cls, df: pd.DataFrame) -> pd.Series:
        """
        Step 2: scan Campaign Name for an APR… parent ID.
        Returns a Series of "ParentGroup_<ID>" strings; NaN where not found.
        Only Campaign Name is checked — intentional hard boundary.
        """
        raw = cls._extract_from(df, _PARENT_SOURCE_COL, _PARENT_RE)
        # Prepend prefix only for matched rows; leave NaN rows as NaN.
        return raw.where(raw.isna(), _PARENT_PREFIX + raw.fillna(""))

    @classmethod
    def _build_entity_series(cls, df: pd.DataFrame) -> pd.Series:
        """
        Combine steps 1 → 2 → default into a single resolved Series.
        No iterrows; every operation is a vectorised pandas call.
        """
        child_asins = cls._step1_child_asin(df)    # NaN = unresolved
        parent_groups = cls._step2_parent_group(df) # NaN = unresolved

        return (
            child_asins
            .fillna(parent_groups)                 # fall back to parent group
            .fillna(_DEFAULT_LABEL)                # hard default
        )
