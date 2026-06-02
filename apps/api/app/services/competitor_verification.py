"""Manual Amazon-result evidence verification for competitor keywords."""

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import (
    CompetitorCleanedRow,
    CompetitorReference,
    CompetitorVerificationEvidenceRow,
    CompetitorVerificationTextEvidenceRow,
)
from apps.api.app.services.amazon_search_agent import AmazonSearchAgentOptions, AmazonSearchEvidenceAgent

VERIFICATION_PAGE_SIZE = 500
TOP_RESULTS_CHECKED = 15
DEFAULT_REQUIRED_MATCH_COUNT = 3
ASIN_PATTERN = re.compile(r"\bB[0-9A-Z]{9}\b", re.IGNORECASE)


@dataclass(frozen=True)
class VerificationResult:
    verified_count: int
    unverified_count: int
    total_count: int
    preview_rows: list[CompetitorCleanedRow]


@dataclass(frozen=True)
class _Competitor:
    key: str
    name: str
    asin: str | None


class CompetitorVerificationService:
    """Verify approved keywords from user-provided Amazon top-result evidence.

    Evidence is deterministic and auditable: a keyword is verified only when at
    least ``required_match_count`` distinct original competitors are explicitly
    matched in positions 1-15 of that keyword's Amazon result evidence.
    """

    def __init__(self, repository: CompetitorCleanedRepository) -> None:
        self._repository = repository

    def verify(
        self,
        *,
        workspace_id: UUID,
        upload_id: UUID,
        competitors: list[str | dict | CompetitorReference],
        evidence_rows: list[CompetitorVerificationEvidenceRow | dict] | None = None,
        evidence_text_rows: list[CompetitorVerificationTextEvidenceRow | dict] | None = None,
        required_match_count: int = DEFAULT_REQUIRED_MATCH_COUNT,
        verification_method: str = "manual_evidence",
    ) -> VerificationResult:
        upload = self._repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
        if upload is None:
            raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)
        if not competitors:
            raise ApiError(code="COMPETITOR_LIST_REQUIRED", message="At least one competitor name or ASIN is required for verification.", status_code=400)
        if required_match_count < 3 or required_match_count > 5:
            raise ApiError(code="INVALID_MATCH_THRESHOLD", message="required_match_count must be between 3 and 5.", status_code=400)

        normalized_competitors = _normalize_competitors(competitors)
        if not normalized_competitors:
            raise ApiError(code="COMPETITOR_LIST_REQUIRED", message="At least one competitor name or ASIN is required for verification.", status_code=400)
        evidence_by_term = _evidence_by_search_term(
            evidence_rows=evidence_rows or [],
            evidence_text_rows=evidence_text_rows or [],
        )

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

            updated: list[CompetitorCleanedRow] = []
            for row in rows:
                if row.scoring_status != "approved" or row.relevance_score is None or row.relevance_score < 3:
                    updated_row = row.model_copy(update={
                        "verification_status": "unverified",
                        "verification_result_json": {
                            "reason": "not_approved_for_verification",
                            "verification_method": verification_method,
                            "required_match_count": required_match_count,
                            "top_results_checked": TOP_RESULTS_CHECKED,
                        },
                        "verified_at": now,
                    })
                    unverified_total += 1
                    updated.append(updated_row)
                    continue

                evaluation = _evaluate_row(
                    search_term=row.search_term or "",
                    competitors=normalized_competitors,
                    evidence=evidence_by_term.get(_normalize_text(row.search_term or "")),
                    required_match_count=required_match_count,
                    verification_method=verification_method,
                )
                verified = evaluation["verified"]
                if verified:
                    verified_total += 1
                else:
                    unverified_total += 1
                updated.append(row.model_copy(update={
                    "verification_status": "verified" if verified else "unverified",
                    "verification_result_json": evaluation,
                    "verified_at": now,
                }))

            self._repository.update_verification_rows(rows=updated)
            all_rows.extend(updated)
            if page * VERIFICATION_PAGE_SIZE >= total:
                break
            page += 1

        return VerificationResult(
            verified_count=verified_total,
            unverified_count=unverified_total,
            total_count=len(all_rows),
            preview_rows=all_rows[:20],
        )

    def verify_with_browser_agent(
        self,
        *,
        workspace_id: UUID,
        upload_id: UUID,
        competitors: list[str | dict | CompetitorReference],
        required_match_count: int = DEFAULT_REQUIRED_MATCH_COUNT,
        max_keywords: int = 25,
        marketplace: str = "US",
        headless: bool = True,
        timeout_ms: int = 15000,
        search_agent: AmazonSearchEvidenceAgent | None = None,
    ) -> tuple[VerificationResult, list[CompetitorVerificationEvidenceRow]]:
        search_terms = self._approved_search_terms(
            workspace_id=workspace_id,
            upload_id=upload_id,
            max_keywords=max_keywords,
        )
        if not search_terms:
            raise ApiError(
                code="NO_APPROVED_KEYWORDS_TO_VERIFY",
                message="Score the upload first. Agentic verification needs approved competitor keywords.",
                status_code=409,
            )
        agent = search_agent or AmazonSearchEvidenceAgent()
        evidence_rows = agent.collect(
            search_terms=search_terms,
            options=AmazonSearchAgentOptions(
                marketplace=marketplace,
                max_results=TOP_RESULTS_CHECKED,
                timeout_ms=timeout_ms,
                headless=headless,
            ),
        )
        result = self.verify(
            workspace_id=workspace_id,
            upload_id=upload_id,
            competitors=competitors,
            evidence_rows=evidence_rows,
            required_match_count=required_match_count,
            verification_method="agentic_browser_search",
        )
        return result, evidence_rows

    def _approved_search_terms(self, *, workspace_id: UUID, upload_id: UUID, max_keywords: int) -> list[str]:
        if max_keywords < 1 or max_keywords > 100:
            raise ApiError(code="INVALID_AGENTIC_BATCH_SIZE", message="max_keywords must be between 1 and 100.", status_code=400)
        terms: list[str] = []
        page = 1
        while len(terms) < max_keywords:
            rows, total = self._repository.list_rows(
                workspace_id=workspace_id,
                competitor_upload_id=upload_id,
                page=page,
                page_size=VERIFICATION_PAGE_SIZE,
            )
            if not rows:
                break
            for row in rows:
                if row.scoring_status == "approved" and row.relevance_score is not None and row.relevance_score >= 3 and row.search_term:
                    terms.append(row.search_term)
                    if len(terms) >= max_keywords:
                        break
            if page * VERIFICATION_PAGE_SIZE >= total:
                break
            page += 1
        return terms


def _normalize_competitors(competitors: list[str | dict | CompetitorReference]) -> list[_Competitor]:
    normalized: list[_Competitor] = []
    seen: set[str] = set()
    for item in competitors:
        if isinstance(item, str):
            name = item.strip()
            asin = None
        elif isinstance(item, CompetitorReference):
            name = item.name.strip()
            asin = item.asin.strip().upper() if item.asin else None
        else:
            name = str(item.get("name", "")).strip()
            asin_value = item.get("asin")
            asin = str(asin_value).strip().upper() if asin_value else None
        if not name and not asin:
            continue
        key = asin or _normalize_text(name)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(_Competitor(key=key, name=name or asin or "competitor", asin=asin))
    return normalized


def _evidence_by_search_term(
    *,
    evidence_rows: list[CompetitorVerificationEvidenceRow | dict],
    evidence_text_rows: list[CompetitorVerificationTextEvidenceRow | dict],
) -> dict[str, CompetitorVerificationEvidenceRow]:
    evidence: dict[str, CompetitorVerificationEvidenceRow] = {}
    for item in evidence_rows:
        row = item if isinstance(item, CompetitorVerificationEvidenceRow) else CompetitorVerificationEvidenceRow.model_validate(item)
        key = _normalize_text(row.search_term)
        if key:
            evidence[key] = row
    for item in evidence_text_rows:
        text_row = item if isinstance(item, CompetitorVerificationTextEvidenceRow) else CompetitorVerificationTextEvidenceRow.model_validate(item)
        key = _normalize_text(text_row.search_term)
        if key and text_row.pasted_results.strip():
            evidence[key] = _parse_text_evidence(text_row)
    return evidence


def _evaluate_row(
    *,
    search_term: str,
    competitors: list[_Competitor],
    evidence: CompetitorVerificationEvidenceRow | None,
    required_match_count: int,
    verification_method: str,
) -> dict:
    if evidence is None:
        return {
            "search_term": search_term,
            "verified": False,
            "reason": "manual_evidence_missing",
            "competitor_matches_found": 0,
            "matched_competitors": [],
            "required_match_count": required_match_count,
            "top_results_checked": TOP_RESULTS_CHECKED,
            "verification_method": verification_method,
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    competitor_by_name = {_normalize_text(c.name): c for c in competitors if c.name}
    competitor_by_asin = {c.asin: c for c in competitors if c.asin}
    matched: dict[str, dict] = {}
    considered_results: list[dict] = []

    for result in evidence.results:
        if result.position < 1 or result.position > TOP_RESULTS_CHECKED:
            continue
        matched_competitor, match_source = _match_result_to_competitor(
            result=result,
            competitors=competitors,
            competitor_by_name=competitor_by_name,
            competitor_by_asin=competitor_by_asin,
        )
        considered_results.append(result.model_dump(mode="json"))
        if matched_competitor is None:
            continue
        matched[matched_competitor.key] = {
            "name": matched_competitor.name,
            "asin": matched_competitor.asin,
            "position": result.position,
            "result_asin": result.asin,
            "result_title": result.title,
            "match_source": match_source,
        }

    verified = len(matched) >= required_match_count
    return {
        "search_term": search_term,
        "verified": verified,
        "reason": "manual_evidence_threshold_met" if verified else "manual_evidence_below_threshold",
        "competitor_matches_found": len(matched),
        "matched_competitors": list(matched.values()),
        "required_match_count": required_match_count,
        "top_results_checked": TOP_RESULTS_CHECKED,
        "evidence_results": considered_results,
        "verification_method": verification_method,
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    }


def _parse_text_evidence(text_row: CompetitorVerificationTextEvidenceRow) -> CompetitorVerificationEvidenceRow:
    results = []
    position = 1
    for raw_line in text_row.pasted_results.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        cleaned = re.sub(r"^\s*(?:#?\d{1,2}[\).:-]\s*|\d{1,2}\s+)", "", line).strip()
        asin_match = ASIN_PATTERN.search(cleaned)
        asin = asin_match.group(0).upper() if asin_match else None
        if asin:
            cleaned = cleaned.replace(asin_match.group(0), "").strip(" -|:\t")
        results.append({
            "position": position,
            "title": cleaned or line,
            "asin": asin,
        })
        position += 1
        if position > TOP_RESULTS_CHECKED:
            break
    return CompetitorVerificationEvidenceRow(search_term=text_row.search_term, results=results)


def _match_result_to_competitor(
    *,
    result,
    competitors: list[_Competitor],
    competitor_by_name: dict[str, _Competitor],
    competitor_by_asin: dict[str, _Competitor],
) -> tuple[_Competitor | None, str | None]:
    if result.matched_competitor_asin:
        matched = competitor_by_asin.get(result.matched_competitor_asin.strip().upper())
        if matched:
            return matched, "explicit_matched_competitor_asin"
    if result.matched_competitor_name:
        matched = competitor_by_name.get(_normalize_text(result.matched_competitor_name))
        if matched:
            return matched, "explicit_matched_competitor_name"
    if result.asin:
        matched = competitor_by_asin.get(result.asin.strip().upper())
        if matched:
            return matched, "result_asin"

    normalized_title = _normalize_text(result.title or "")
    if not normalized_title:
        return None, None
    for competitor in competitors:
        normalized_name = _normalize_text(competitor.name)
        if normalized_name and normalized_name in normalized_title:
            return competitor, "result_title_name"
    return None, None


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())
