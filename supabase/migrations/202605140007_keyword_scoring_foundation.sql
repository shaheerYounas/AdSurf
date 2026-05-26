create type keyword_scoring_run_status as enum (
    'running',
    'succeeded',
    'failed'
);

create type keyword_candidate_status as enum (
    'approved',
    'rejected',
    'error'
);

alter table upload_column_mappings
    add constraint upload_column_mappings_scope_identity_key
    unique (id, workspace_id, product_id, upload_id, parse_run_id);

create table keyword_scoring_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    product_id uuid not null references product_profiles(id) on delete cascade,
    upload_id uuid not null references uploads(id) on delete cascade,
    parse_run_id uuid not null,
    column_mapping_id uuid not null,
    status keyword_scoring_run_status not null,
    scoring_version integer not null,
    rule_version_id uuid null references rule_versions(id),
    idempotency_key text not null,
    total_rows integer not null default 0 check (total_rows >= 0),
    scored_rows integer not null default 0 check (scored_rows >= 0),
    approved_count integer not null default 0 check (approved_count >= 0),
    rejected_count integer not null default 0 check (rejected_count >= 0),
    error_count integer not null default 0 check (error_count >= 0),
    started_at timestamptz not null default now(),
    completed_at timestamptz null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    error_message text null,
    unique (column_mapping_id, scoring_version),
    unique (workspace_id, idempotency_key),
    constraint keyword_scoring_runs_mapping_scope_fk
        foreign key (column_mapping_id, workspace_id, product_id, upload_id, parse_run_id)
        references upload_column_mappings(id, workspace_id, product_id, upload_id, parse_run_id),
    constraint keyword_scoring_runs_scope_identity_key
        unique (id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)
);

create table keyword_candidates (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    product_id uuid not null references product_profiles(id) on delete cascade,
    upload_id uuid not null references uploads(id) on delete cascade,
    parse_run_id uuid not null,
    column_mapping_id uuid not null,
    scoring_run_id uuid not null,
    source_row_id uuid not null,
    search_term text null,
    search_volume numeric null,
    competitor_rank_values_json jsonb not null default '[]'::jsonb,
    relevance_score integer null check (relevance_score is null or relevance_score between 0 and 10),
    scoring_status keyword_candidate_status not null,
    rejection_reason text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint keyword_candidates_scoring_run_scope_fk
        foreign key (scoring_run_id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)
        references keyword_scoring_runs(id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)
        on delete cascade,
    constraint keyword_candidates_search_term_required_for_scored
        check (scoring_status = 'error' or nullif(btrim(search_term), '') is not null)
);

create index keyword_scoring_runs_workspace_upload_idx
    on keyword_scoring_runs(workspace_id, upload_id, created_at desc);
create index keyword_candidates_workspace_product_idx
    on keyword_candidates(workspace_id, product_id);
create index keyword_candidates_upload_idx
    on keyword_candidates(upload_id);
create index keyword_candidates_scoring_run_idx
    on keyword_candidates(scoring_run_id);
create index keyword_candidates_scoring_status_idx
    on keyword_candidates(scoring_status);
create index keyword_candidates_relevance_score_idx
    on keyword_candidates(relevance_score);
create index keyword_candidates_search_term_idx
    on keyword_candidates(search_term);

alter table keyword_scoring_runs enable row level security;
alter table keyword_candidates enable row level security;

create policy keyword_scoring_runs_select_workspace_members
on keyword_scoring_runs for select
using (public.current_user_is_workspace_member(workspace_id));

create policy keyword_candidates_select_workspace_members
on keyword_candidates for select
using (public.current_user_is_workspace_member(workspace_id));

comment on table keyword_scoring_runs is 'Deterministic keyword relevance scoring runs. Batch 6 does not generate campaigns, exports, recommendations, or Amazon Ads API actions.';
comment on table keyword_candidates is 'Row-level keyword relevance outcomes from approved manual column mappings. Duplicate search terms are preserved.';
