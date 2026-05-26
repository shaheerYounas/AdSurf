from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from apps.api.app.schemas.keyword_scoring import KeywordCandidateStatus


class KeywordOverrideAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewedKeywordStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovedKeywordSetStatus(StrEnum):
    CREATED = "created"
    LOCKED = "locked"
    SUPERSEDED = "superseded"


class KeywordCandidateOverrideCreateRequest(BaseModel):
    override_action: KeywordOverrideAction
    reason: str


class KeywordCandidateOverride(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    scoring_run_id: UUID
    keyword_candidate_id: UUID
    override_action: KeywordOverrideAction
    original_scoring_status: KeywordCandidateStatus
    new_status: ReviewedKeywordStatus
    reason: str
    created_by: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KeywordCandidateReview(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    column_mapping_id: UUID
    scoring_run_id: UUID
    source_row_id: UUID
    search_term: str | None = None
    search_volume: Decimal | None = None
    relevance_score: int | None = None
    original_scoring_status: KeywordCandidateStatus
    effective_status: KeywordCandidateStatus
    rejection_reason: str | None = None
    override: KeywordCandidateOverride | None = None

    model_config = ConfigDict(from_attributes=True)


class ApprovedKeywordSetCreateRequest(BaseModel):
    name: str


class ApprovedKeywordSet(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    scoring_run_id: UUID
    column_mapping_id: UUID
    name: str
    status: ApprovedKeywordSetStatus
    keyword_count: int
    created_by: UUID
    created_at: datetime
    approved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ApprovedKeywordSetItem(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    approved_keyword_set_id: UUID
    scoring_run_id: UUID
    keyword_candidate_id: UUID
    search_term: str
    search_volume: Decimal | None = None
    relevance_score: int
    source_status: KeywordCandidateStatus
    final_status: ReviewedKeywordStatus
    override_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
