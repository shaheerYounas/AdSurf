-- Phase 2: Relevance Score columns on competitor_cleaned_rows
-- The scoring formula: competitor rank < 15 increments a 0-10 score.
-- Rows scoring 3+ are APPROVED; rows scoring 0-2 are REJECTED.
-- This avoids duplicating the full keyword_scoring_runs/candidates tables
-- and keeps the Phase 1 pipeline self-contained.

alter table competitor_cleaned_rows
    add column relevance_score integer null check (relevance_score is null or relevance_score between 0 and 10),
    add column scoring_status text null check (scoring_status in ('approved', 'rejected', 'error')),
    add column rejection_reason text null,
    add column scored_at timestamptz null;

create index competitor_cleaned_rows_relevance_score_idx
    on competitor_cleaned_rows(relevance_score);

create index competitor_cleaned_rows_scoring_status_idx
    on competitor_cleaned_rows(scoring_status);

comment on column competitor_cleaned_rows.relevance_score is 'Relevance score from 0-10. One point per competitor with organic rank < 15.';
comment on column competitor_cleaned_rows.scoring_status is 'approved (score >= 3), rejected (score 0-2), or error.';
comment on column competitor_cleaned_rows.rejection_reason is 'Reason when scoring_status is rejected or error.';
comment on column competitor_cleaned_rows.scored_at is 'Timestamp when scoring was last applied.';