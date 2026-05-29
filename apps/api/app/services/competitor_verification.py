"""Amazon search verification for competitor keywords (items 5-7).

Uses a simulated PAAPI call. In production, replace _search_amazon() with actual
Amazon Product Advertising API 5.0 SearchItems calls.
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow, CompetitorUpload

VERIFICATION_PAGE_SIZE = 500
SEARCH_RESULTS_COUNT = 12
MIN_COMPETITOR_MATCHES = 3
MAX_COMPETITOR_MATCHES = 5


@dataclass(frozen=True)
class VerificationResult:
    verified_count: int
    unverified_count: int
    total_count: int
    preview_rows: list[CompetitorCleanedRow]


class CompetitorVerificationService:
    """Simulated Amazon search verification.

    In the MVP this uses a rule-based simulation because:
    - PAAPI requires Amazon Associates approval and has rate limits (1 TPS default)
    - Scraping Amazon violates ToS and is unreliable
    - The plan's "manual check" can be approximated until real PAAPI integration

    When PAAPI credentials are available, replace _search_amazon() with:
        paapi = boto3.client(...)
        response = paapi.search_items(Keywords=search_term, ...)
        organic_results = [item['ASIN'] for item in response['SearchResult']['Items']]
    """

    def __init__(self, repository: CompetitorCleanedRepository) -> None:
        self._repository = repository

    def verify(
        self,
        *,
        workspace_id: UUID,
        upload_id: UUID,
        competitors: list[str],
    ) -> VerificationResult:
        upload = self._repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
        if upload is None:
            raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)
        if not competitors:
            raise ApiError(code="COMPETITOR_LIST_REQUIRED", message="At least one competitor name is required for verification.", status_code=400)

        verified_total = 0
        unverified_total = 0
        all_rows: list[CompetitorCleanedRow] = []
        page = 1
        now = datetime.now(UTC)

        while True:
            rows, total = self._repository.list_rows(
                workspace_id=workspace_id,
                competitor_upload_id=upload_id,
                page=page,
                page_size=VERIFICATION_PAGE_SIZE,
            )
            if not rows:
                break

            # Only verify approved scored rows
            approved = [r for r in rows if r.scoring_status == "approved" and r.relevance_score is not None and r.relevance_score >= 3]
            updated: list[CompetitorCleanedRow] = []
            for row in approved:
                matches = self._search_amazon(search_term=row.search_term or "", competitors=competitors)
                threshold = random.randint(MIN_COMPETITOR_MATCHES, MAX_COMPETITOR_MATCHES)
                verified = matches >= threshold
                if verified:
                    verified_total += 1
                else:
                    unverified_total += 1
                updated.append(row.model_copy(update={
                    "verification_status": "verified" if verified else "unverified",
                    "verification_result_json": {
                        "search_term": row.search_term,
                        "competitors_checked": competitors,
                        "competitor_matches_found": matches,
                        "match_threshold": threshold,
                        "verified": verified,
                        "verification_method": "simulated_paapi",
                    },
                    "verified_at": now,
                }))

            # Update non-approved rows too (mark them as unverified so all rows have a status)
            for row in rows:
                if row.scoring_status != "approved" or row.relevance_score is None or row.relevance_score < 3:
                    if row.verification_status is None:
                        updated.append(row.model_copy(update={
                            "verification_status": "unverified",
                            "verification_result_json": {"reason": "not_approved_for_verification"},
                            "verified_at": now,
                        }))

            self._repository.update_verification_rows(rows=updated)
            all_rows.extend(updated)
            if page * VERIFICATION_PAGE_SIZE >= total:
                break
            page += 1

        return VerificationResult(
            verified_count=verified_total,
            unverified_count=unverified_total + (len(all_rows) - verified_total - unverified_total),
            total_count=len(all_rows),
            preview_rows=all_rows[:20],
        )

    def _search_amazon(self, *, search_term: str, competitors: list[str]) -> int:
        """Simulated Amazon search. Returns number of competitors found in top results.

        In production: calls Amazon PAAPI SearchItems with search_term,
        extracts top SEARCH_RESULTS_COUNT organic results,
        counts how many product competitors appear (by name or ASIN).
        """
        if not search_term or not competitors:
            return 0
        # Simulation: each competitor has ~40% chance of appearing in results
        # This produces reasonable 0-10 match counts matching the plan's 3-5 threshold
        matches = 0
        for _ in range(SEARCH_RESULTS_COUNT):
            for competitor in competitors:
                if random.random() < 0.40:
                    matches += 1
        return min(matches, len(competitors))