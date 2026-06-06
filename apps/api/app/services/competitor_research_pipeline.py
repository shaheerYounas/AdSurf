"""Competitor Research Pipeline — Phase 1 of the Marketing Project.

Consumes competitor+keyword rows (one row per competitor per keyword) and produces
a list of approved keywords that passed scoring and simulated Amazon verification.

Design constraints:
  - Pure service: no DB, no HTTP, no side effects.
  - Amazon verification is simulated via deterministic heuristics (search_volume > 100
    AND relevance_score >= 5) since real HTTP is out of scope.
  - parse_csv_rows handles case-insensitive column name variants.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Header normalization
# ---------------------------------------------------------------------------

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm_key(header: str) -> str:
    """Lower + collapse non-alphanumeric runs to single space, then strip."""
    return _NORM_RE.sub(" ", header.strip().lower()).strip()


# Map normalized header key → canonical field name.
# Covers common variants: spaced, underscored, mixed-case.
_COLUMN_MAP: dict[str, str] = {
    "keyword": "keyword",
    "search volume": "search_volume",
    "search_volume": "search_volume",
    "organic rank": "organic_rank",
    "organic_rank": "organic_rank",
    "competitor id": "competitor_id",
    "competitor_id": "competitor_id",
}

_REQUIRED_CANONICAL: frozenset[str] = frozenset({
    "keyword",
    "search_volume",
    "organic_rank",
    "competitor_id",
})


# ---------------------------------------------------------------------------
# Input dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompetitorRow:
    keyword: str
    search_volume: int
    organic_rank: int
    competitor_id: str


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ApprovedKeyword:
    keyword: str
    search_volume: int
    relevance_score: int
    amazon_verified: bool


@dataclass
class ResearchPipelineResult:
    approved_keywords: list[ApprovedKeyword] = field(default_factory=list)
    total_input_keywords: int = 0   # unique keywords before scoring
    filtered_by_score: int = 0      # dropped because score <= 2
    filtered_by_amazon: int = 0     # dropped because amazon_verified=False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

class CompetitorResearchPipeline:
    """Pure service that runs the competitor research scoring pipeline.

    Usage::

        pipeline = CompetitorResearchPipeline()
        result = pipeline.run(rows=parsed_rows, product_name="CoffeeMaker")
    """

    def run(
        self,
        rows: list[CompetitorRow],
        product_name: str,  # noqa: ARG002 — reserved for future campaign naming
    ) -> ResearchPipelineResult:
        """Execute the full pipeline and return a ResearchPipelineResult.

        Steps
        -----
        1. Clean  — deduplicate by (keyword, competitor_id); group by keyword.
        2. Score  — count competitors with organic_rank < 15; drop score <= 2.
        3. Verify — simulate Amazon check; drop amazon_verified=False.
        """
        # Step 1 — Clean: deduplicate and group by keyword
        grouped = self._clean(rows)
        total_input_keywords = len(grouped)

        # Step 2 — Score
        scored: dict[str, tuple[int, int]] = {}  # keyword → (search_volume, relevance_score)
        for keyword, kw_rows in grouped.items():
            score = sum(1 for r in kw_rows if r.organic_rank < 15)
            if score <= 2:
                continue
            # Take search_volume from the first row for this keyword (all rows for the
            # same keyword share the same search volume in the source report).
            sv = kw_rows[0].search_volume
            scored[keyword] = (sv, score)

        filtered_by_score = total_input_keywords - len(scored)

        # Step 3 — Amazon verification (simulated)
        approved: list[ApprovedKeyword] = []
        for keyword, (sv, score) in scored.items():
            verified = self._simulate_amazon_verification(sv, score)
            if verified:
                approved.append(ApprovedKeyword(
                    keyword=keyword,
                    search_volume=sv,
                    relevance_score=score,
                    amazon_verified=True,
                ))

        filtered_by_amazon = len(scored) - len(approved)

        # Sort descending by relevance_score then search_volume for deterministic output
        approved.sort(key=lambda k: (-k.relevance_score, -k.search_volume))

        return ResearchPipelineResult(
            approved_keywords=approved,
            total_input_keywords=total_input_keywords,
            filtered_by_score=filtered_by_score,
            filtered_by_amazon=filtered_by_amazon,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clean(self, rows: list[CompetitorRow]) -> dict[str, list[CompetitorRow]]:
        """Deduplicate by (keyword, competitor_id) and group rows by keyword.

        Returns an ordered dict: keyword → list of unique CompetitorRow objects.
        Insertion order is preserved so output is deterministic.
        """
        seen: set[tuple[str, str]] = set()
        grouped: dict[str, list[CompetitorRow]] = {}

        for row in rows:
            dedup_key = (row.keyword, row.competitor_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            grouped.setdefault(row.keyword, []).append(row)

        return grouped

    def _simulate_amazon_verification(
        self, search_volume: int, relevance_score: int
    ) -> bool:
        """Simulate checking Amazon search results.

        Approximates whether 3–5 of the original competitors appear in the top
        10–15 Amazon results by checking two proxy signals:
          - search_volume > 100  (keyword is actively searched)
          - relevance_score >= 5 (majority of top competitors already rank for it)
        """
        return search_volume > 100 and relevance_score >= 5


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_csv_rows(csv_text: str) -> list[CompetitorRow]:
    """Parse CSV text and return a list of CompetitorRow objects.

    Column names are matched case-insensitively. Accepted variants:

    - keyword      / Keyword
    - search_volume / Search Volume
    - organic_rank  / Organic Rank
    - competitor_id / Competitor ID

    Raises
    ------
    ValueError
        If any required column is absent from the CSV headers, with a clear
        message listing which columns are missing.
    ValueError
        If a row contains a non-integer value where an integer is required.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))

    if reader.fieldnames is None:
        raise ValueError("CSV appears to be empty — no headers found.")

    # Build a mapping from raw header → canonical field name
    header_map: dict[str, str] = {}
    canonical_found: set[str] = set()
    for raw_header in reader.fieldnames:
        key = _norm_key(raw_header)
        canonical = _COLUMN_MAP.get(key)
        if canonical and canonical not in canonical_found:
            header_map[raw_header] = canonical
            canonical_found.add(canonical)

    missing = sorted(_REQUIRED_CANONICAL - canonical_found)
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {missing}. "
            f"Headers found: {list(reader.fieldnames)}"
        )

    # Reverse map: canonical → raw header (for lookup in each row dict)
    canonical_to_raw: dict[str, str] = {v: k for k, v in header_map.items()}

    rows: list[CompetitorRow] = []
    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is headers
        keyword_raw = canonical_to_raw["keyword"]
        sv_raw = canonical_to_raw["search_volume"]
        rank_raw = canonical_to_raw["organic_rank"]
        cid_raw = canonical_to_raw["competitor_id"]

        keyword = (row.get(keyword_raw) or "").strip()
        search_volume_str = (row.get(sv_raw) or "").strip().replace(",", "")
        organic_rank_str = (row.get(rank_raw) or "").strip().replace(",", "")
        competitor_id = (row.get(cid_raw) or "").strip()

        if not keyword:
            continue  # skip blank keyword rows (e.g. trailing empty lines)

        try:
            search_volume = int(float(search_volume_str))
        except (ValueError, TypeError):
            raise ValueError(
                f"Row {row_num}: 'search_volume' must be an integer, "
                f"got {search_volume_str!r} for keyword {keyword!r}."
            )

        try:
            organic_rank = int(float(organic_rank_str))
        except (ValueError, TypeError):
            raise ValueError(
                f"Row {row_num}: 'organic_rank' must be an integer, "
                f"got {organic_rank_str!r} for keyword {keyword!r}."
            )

        rows.append(CompetitorRow(
            keyword=keyword,
            search_volume=search_volume,
            organic_rank=organic_rank,
            competitor_id=competitor_id,
        ))

    return rows
