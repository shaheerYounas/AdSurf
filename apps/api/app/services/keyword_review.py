from datetime import UTC, datetime
import json
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.keyword_review import KeywordReviewRepository
from apps.api.app.repositories.keyword_scoring import KeywordScoringRepository
from apps.api.app.schemas.keyword_review import (
    ApprovedKeywordSet,
    ApprovedKeywordSetItem,
    ApprovedKeywordSetStatus,
    KeywordCandidateOverride,
    KeywordCandidateReview,
    KeywordOverrideAction,
    ReviewedKeywordStatus,
)
from apps.api.app.schemas.keyword_scoring import KeywordCandidate, KeywordCandidateStatus, KeywordScoringRunStatus
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet


REVIEW_ROWS_PAGE_SIZE = 500


class KeywordReviewService:
    def __init__(self, *, scoring_repository: KeywordScoringRepository, review_repository: KeywordReviewRepository) -> None:
        self._scoring_repository = scoring_repository
        self._review_repository = review_repository

    def create_override(
        self,
        *,
        workspace_id: UUID,
        keyword_candidate_id: UUID,
        override_action: KeywordOverrideAction,
        reason: str,
        created_by: UUID,
    ) -> KeywordCandidateOverride:
        trimmed_reason = reason.strip()
        if not trimmed_reason:
            raise ApiError(code="OVERRIDE_REASON_REQUIRED", message="Override reason is required.", status_code=400)

        candidate = self._scoring_repository.get_candidate(workspace_id=workspace_id, candidate_id=keyword_candidate_id)
        if candidate is None:
            raise ApiError(code="KEYWORD_CANDIDATE_NOT_FOUND", message="Keyword candidate was not found.", status_code=404)
        if candidate.scoring_status == KeywordCandidateStatus.ERROR:
            raise ApiError(code="KEYWORD_CANDIDATE_NOT_OVERRIDABLE", message="Error candidates cannot be overridden in the MVP.", status_code=409)

        existing = self._review_repository.get_override_for_candidate(workspace_id=workspace_id, keyword_candidate_id=keyword_candidate_id)
        if existing is not None:
            raise ApiError(code="KEYWORD_CANDIDATE_OVERRIDE_EXISTS", message="Keyword candidate already has an override.", status_code=409)

        new_status = ReviewedKeywordStatus.APPROVED if override_action == KeywordOverrideAction.APPROVE else ReviewedKeywordStatus.REJECTED
        if candidate.scoring_status.value == new_status.value:
            raise ApiError(code="KEYWORD_CANDIDATE_OVERRIDE_NOOP", message="Override would not change the candidate status.", status_code=409)

        now = datetime.now(UTC)
        override = KeywordCandidateOverride(
            id=uuid4(),
            workspace_id=candidate.workspace_id,
            product_id=candidate.product_id,
            scoring_run_id=candidate.scoring_run_id,
            keyword_candidate_id=candidate.id,
            override_action=override_action,
            original_scoring_status=candidate.scoring_status,
            new_status=new_status,
            reason=trimmed_reason,
            created_by=created_by,
            created_at=now,
        )
        return self._review_repository.create_override(override=override)

    def list_reviews(
        self,
        *,
        workspace_id: UUID,
        scoring_run_id: UUID,
        effective_status: KeywordCandidateStatus | None,
        original_status: KeywordCandidateStatus | None,
        has_override: bool | None,
        min_relevance_score: int | None,
        max_relevance_score: int | None,
        search_term: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KeywordCandidateReview], int]:
        run = self._scoring_repository.get_run(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
        if run is None:
            raise ApiError(code="KEYWORD_SCORING_RUN_NOT_FOUND", message="Keyword scoring run was not found.", status_code=404)

        candidates = self._load_candidates(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
        overrides = {
            override.keyword_candidate_id: override
            for override in self._review_repository.list_overrides_for_scoring_run(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
        }
        reviews = [_review_from_candidate(candidate=candidate, override=overrides.get(candidate.id)) for candidate in candidates]
        if effective_status is not None:
            reviews = [review for review in reviews if review.effective_status == effective_status]
        if original_status is not None:
            reviews = [review for review in reviews if review.original_scoring_status == original_status]
        if has_override is not None:
            reviews = [review for review in reviews if (review.override is not None) == has_override]
        if min_relevance_score is not None:
            reviews = [review for review in reviews if review.relevance_score is not None and review.relevance_score >= min_relevance_score]
        if max_relevance_score is not None:
            reviews = [review for review in reviews if review.relevance_score is not None and review.relevance_score <= max_relevance_score]
        if search_term:
            normalized = search_term.strip().lower()
            reviews = [review for review in reviews if normalized in (review.search_term or "").lower()]

        total = len(reviews)
        start = (page - 1) * page_size
        return reviews[start : start + page_size], total

    def create_approved_keyword_set(
        self,
        *,
        workspace_id: UUID,
        scoring_run_id: UUID,
        name: str,
        created_by: UUID,
    ) -> ApprovedKeywordSet:
        trimmed_name = name.strip()
        if not trimmed_name:
            raise ApiError(code="APPROVED_KEYWORD_SET_NAME_REQUIRED", message="Approved keyword set name is required.", status_code=400)

        run = self._scoring_repository.get_run(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
        if run is None:
            raise ApiError(code="KEYWORD_SCORING_RUN_NOT_FOUND", message="Keyword scoring run was not found.", status_code=404)
        if run.status != KeywordScoringRunStatus.SUCCEEDED:
            raise ApiError(code="KEYWORD_SCORING_RUN_NOT_COMPLETE", message="Only succeeded scoring runs can be snapshotted.", status_code=409)

        reviews, _ = self.list_reviews(
            workspace_id=workspace_id,
            scoring_run_id=scoring_run_id,
            effective_status=KeywordCandidateStatus.APPROVED,
            original_status=None,
            has_override=None,
            min_relevance_score=None,
            max_relevance_score=None,
            search_term=None,
            page=1,
            page_size=100_000,
        )
        reviews = [review for review in reviews if review.original_scoring_status != KeywordCandidateStatus.ERROR and review.search_term]
        if not reviews:
            raise ApiError(code="APPROVED_KEYWORD_SET_EMPTY", message="Approved keyword set requires at least one approved candidate.", status_code=409)

        now = datetime.now(UTC)
        keyword_set = ApprovedKeywordSet(
            id=uuid4(),
            workspace_id=run.workspace_id,
            product_id=run.product_id,
            scoring_run_id=run.id,
            column_mapping_id=run.column_mapping_id,
            name=trimmed_name,
            status=ApprovedKeywordSetStatus.LOCKED,
            keyword_count=len(reviews),
            created_by=created_by,
            created_at=now,
            approved_at=now,
        )
        items = [
            ApprovedKeywordSetItem(
                id=uuid4(),
                workspace_id=review.workspace_id,
                product_id=review.product_id,
                approved_keyword_set_id=keyword_set.id,
                scoring_run_id=review.scoring_run_id,
                keyword_candidate_id=review.id,
                search_term=review.search_term or "",
                search_volume=review.search_volume,
                relevance_score=review.relevance_score or 0,
                source_status=review.original_scoring_status,
                final_status=ReviewedKeywordStatus.APPROVED,
                override_id=review.override.id if review.override else None,
                created_at=now,
            )
            for review in reviews
        ]
        return self._review_repository.create_keyword_set(keyword_set=keyword_set, items=items)

    def get_keyword_set(self, *, workspace_id: UUID, keyword_set_id: UUID) -> ApprovedKeywordSet:
        keyword_set = self._review_repository.get_keyword_set(workspace_id=workspace_id, keyword_set_id=keyword_set_id)
        if keyword_set is None:
            raise ApiError(code="APPROVED_KEYWORD_SET_NOT_FOUND", message="Approved keyword set was not found.", status_code=404)
        return keyword_set

    def list_keyword_set_items(
        self,
        *,
        workspace_id: UUID,
        keyword_set_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ApprovedKeywordSetItem], int]:
        self.get_keyword_set(workspace_id=workspace_id, keyword_set_id=keyword_set_id)
        return self._review_repository.list_keyword_set_items(
            workspace_id=workspace_id,
            keyword_set_id=keyword_set_id,
            page=page,
            page_size=page_size,
        )

    def _load_candidates(self, *, workspace_id: UUID, scoring_run_id: UUID) -> list[KeywordCandidate]:
        candidates: list[KeywordCandidate] = []
        page = 1
        while True:
            page_candidates, total = self._scoring_repository.list_candidates(
                workspace_id=workspace_id,
                scoring_run_id=scoring_run_id,
                scoring_status=None,
                min_relevance_score=None,
                max_relevance_score=None,
                search_term=None,
                page=page,
                page_size=REVIEW_ROWS_PAGE_SIZE,
            )
            candidates.extend(page_candidates)
            if page * REVIEW_ROWS_PAGE_SIZE >= total:
                return candidates
            page += 1


def _review_from_candidate(*, candidate: KeywordCandidate, override: KeywordCandidateOverride | None) -> KeywordCandidateReview:
    if override is None:
        effective_status = candidate.scoring_status
    else:
        effective_status = KeywordCandidateStatus(override.new_status.value)
    return KeywordCandidateReview(
        id=candidate.id,
        workspace_id=candidate.workspace_id,
        product_id=candidate.product_id,
        upload_id=candidate.upload_id,
        parse_run_id=candidate.parse_run_id,
        column_mapping_id=candidate.column_mapping_id,
        scoring_run_id=candidate.scoring_run_id,
        source_row_id=candidate.source_row_id,
        search_term=candidate.search_term,
        search_volume=candidate.search_volume,
        relevance_score=candidate.relevance_score,
        original_scoring_status=candidate.scoring_status,
        effective_status=effective_status,
        rejection_reason=candidate.rejection_reason,
        override=override,
    )


# =============================================================================
# Dual-Path Keyword Review: Deterministic + AI
# =============================================================================

KEYWORD_REVIEW_AI_AGENT_ID = "keyword_review_agent"


class DualPathKeywordReview(DualPathDecisionService[list[dict]]):
    """Dual-path keyword review service.

    Deterministic path: review calculation from scored candidates (exact rules).
    AI path: LLM reviews keyword candidates and suggests review decisions.
    Both paths produce the same output schema (list of review dicts).
    """

    AGENT_ID = KEYWORD_REVIEW_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Keyword Review Agent"

    def _deterministic_path(self, inputs: dict) -> list[dict]:
        """Run deterministic keyword review from scored candidates."""
        candidates: list[KeywordCandidate] = inputs["candidates"]
        overrides: dict[UUID, KeywordCandidateOverride] = inputs.get("overrides", {})
        reviews: list[dict] = []
        for candidate in candidates:
            override = overrides.get(candidate.id)
            review = _review_from_candidate(candidate=candidate, override=override)
            reviews.append({
                "search_term": review.search_term,
                "search_volume": str(review.search_volume) if review.search_volume else None,
                "relevance_score": review.relevance_score,
                "original_scoring_status": review.original_scoring_status.value,
                "effective_status": review.effective_status.value,
                "rejection_reason": review.rejection_reason,
                "has_override": review.override is not None,
                "decision_source": "deterministic",
                "requires_human_approval": True,
                "executes_live_amazon_change": False,
            })
        return reviews

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        candidates: list[KeywordCandidate] = inputs["candidates"]
        candidates_for_prompt = [
            {
                "search_term": c.search_term,
                "search_volume": str(c.search_volume) if c.search_volume else None,
                "relevance_score": c.relevance_score,
                "scoring_status": c.scoring_status.value,
                "rejection_reason": c.rejection_reason,
            }
            for c in candidates[:200]
        ]

        system = (
            "You are the AdSurf Keyword Review Agent for Amazon Ads keyword review. "
            "Your job is to review scored keyword candidates and suggest approval/rejection decisions. "
            f"{safety_prompt_snippet()}"
            "You suggest review decisions only — they must be approved by a human. "
            "Return JSON only. "
            "Every output must include decision_source='ai' and requires_human_approval=true."
        )
        user = {
            "task": "review_keyword_candidates",
            "candidates": candidates_for_prompt,
            "review_rules": {
                "approve_if_relevance_gte_3": True,
                "error_candidates_not_overridable": True,
            },
            "required_output_shape": {
                "reviews": [
                    {
                        "search_term": "string",
                        "search_volume": "number or null",
                        "relevance_score": "integer",
                        "original_scoring_status": "approved | rejected | error",
                        "effective_status": "approved | rejected",
                        "rejection_reason": "string or null",
                        "review_note": "brief explanation for human reviewer",
                        "decision_source": "ai",
                        "requires_human_approval": True,
                        "executes_live_amazon_change": False,
                    }
                ]
            },
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)},
        ]

    def _validate_ai_output(self, ai_json: dict, inputs: dict) -> list[str]:
        errors: list[str] = []
        reviews = ai_json.get("reviews", [])
        if not reviews:
            errors.append("AI output must include reviews list.")
        for i, review in enumerate(reviews):
            prefix = f"reviews[{i}]"
            status = review.get("effective_status")
            if status not in ("approved", "rejected"):
                errors.append(f"{prefix}.effective_status must be 'approved' or 'rejected'.")
            if review.get("decision_source") != "ai":
                errors.append(f"{prefix}.decision_source must be 'ai'.")
            if review.get("requires_human_approval") is not True:
                errors.append(f"{prefix}.requires_human_approval must be true.")
            if review.get("executes_live_amazon_change") is not False:
                errors.append(f"{prefix}.executes_live_amazon_change must be false.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> list[dict]:
        return ai_json.get("reviews", [])

    def _empty_result(self) -> list[dict]:
        return []
