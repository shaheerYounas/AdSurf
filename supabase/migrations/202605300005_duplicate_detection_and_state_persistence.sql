-- =============================================================================
-- AdSurf Duplicate Detection & State Persistence Enhancement
-- Phase 2-8: file_hash, data_fingerprint, recommendation_fingerprint,
-- status lifecycle additions, and entity key improvements
-- =============================================================================

-- =============================================================================
-- PHASE 2: Exact Duplicate File Detection
-- =============================================================================
alter table uploads
    add column if not exists file_hash text,
    add column if not exists file_hash_algorithm text default 'sha256';

create index if not exists uploads_file_hash_idx on uploads(workspace_id, file_hash);

comment on column uploads.file_hash is 'SHA-256 hash of the raw uploaded file content. Used for exact duplicate detection.';
comment on column uploads.file_hash_algorithm is 'Hashing algorithm used to compute file_hash, currently always sha256.';

-- =============================================================================
-- PHASE 3: Data Fingerprint Detection
-- =============================================================================
alter table account_imports
    add column if not exists data_fingerprint text,
    add column if not exists data_fingerprint_version text default 'v1';

create index if not exists account_imports_fingerprint_idx on account_imports(workspace_id, data_fingerprint);

comment on column account_imports.data_fingerprint is 'Normalized business data fingerprint (hash of workspace, report_type, date_range, row_count, key metrics). Used to detect same-data-different-file duplicates.';
comment on column account_imports.data_fingerprint_version is 'Version of the fingerprint algorithm. Bump when algorithm changes.';

-- =============================================================================
-- PHASE 4: Entity Keys - entities table already has entity_key column
-- Add index to support entity deduplication
-- =============================================================================
create index if not exists account_import_entities_key_idx on account_import_entities(workspace_id, entity_type, entity_key);

-- =============================================================================
-- PHASE 6: Recommendation Fingerprint
-- =============================================================================
alter table recommendations
    add column if not exists recommendation_fingerprint text,
    add column if not exists fingerprint_version text default 'v1',
    add column if not exists superseded_by_id uuid references recommendations(id) on delete set null;

create index if not exists recommendations_fingerprint_idx on recommendations(workspace_id, recommendation_fingerprint);

comment on column recommendations.recommendation_fingerprint is 'Deterministic fingerprint of the recommendation (import_id, type, entity_type, entity_key, current_value, recommended_value, rule_name, strategy). Used to prevent duplicate recommendations.';
comment on column recommendations.superseded_by_id is 'When a newer run produces a recommendation that supersedes this one, points to the newer recommendation.';

-- =============================================================================
-- PHASE 8: Status Lifecycle
-- Add new status values for uploads, imports, workflows, recommendations
-- =============================================================================

-- Upload status: add duplicate_detected and archived
alter type upload_status add value if not exists 'duplicate_detected';
alter type upload_status add value if not exists 'archived';

-- Account import status: add additional lifecycle statuses
-- (The check constraint on account_imports.status needs to be updated)
alter table account_imports
    drop constraint if exists account_imports_status_check;

alter table account_imports
    add constraint account_imports_status_check
    check (
        status in (
            'created',
            'detected',
            'classifying',
            'classified',
            'mapping_columns',
            'normalizing',
            'needs_mapping',
            'ready_for_analysis',
            'processing',
            'succeeded',
            'failed'
        )
    );

-- Workflow/run status: already has good coverage
-- Ensure workflow_status type matches requirements
-- Recommendation status: add new values
alter type recommendation_status add value if not exists 'draft';
alter type recommendation_status add value if not exists 'validated';
alter type recommendation_status add value if not exists 'rejected_by_validator';
alter type recommendation_status add value if not exists 'repeated';
alter type recommendation_status add value if not exists 'conflicting';
alter type recommendation_status add value if not exists 'exported';

-- =============================================================================
-- PHASE 5: Analysis Runs - explicit run relationship
-- =============================================================================

-- Add run_id to recommendations (already has agent_run_id and ai_run_id from earlier migration)
-- Add run_number to track which run within an import
alter table agent_workflows
    add column if not exists run_number integer not null default 1,
    add column if not exists strategy_profile text;

create index if not exists agent_workflows_import_run_idx on agent_workflows(account_import_id, run_number);

comment on column agent_workflows.run_number is 'Sequential run number within a given account import (1, 2, 3...).';
comment on column agent_workflows.strategy_profile is 'Strategy label for this run (e.g., conservative, balanced, growth).';

-- Add duplicate_detected_at and previous_upload_id to uploads
alter table uploads
    add column if not exists duplicate_detected_at timestamptz,
    add column if not exists previous_upload_id uuid references uploads(id) on delete set null,
    add column if not exists duplicate_type text check (duplicate_type in ('exact_file_duplicate', 'same_data_duplicate', null));

comment on column uploads.duplicate_detected_at is 'When duplicate detection flagged this upload.';
comment on column uploads.previous_upload_id is 'Reference to the previous upload that this one duplicates.';
comment on column uploads.duplicate_type is 'Type of duplicate detected: exact_file_duplicate or same_data_duplicate.';

-- =============================================================================
-- Dashboard Summary Cache (for refresh recovery)
-- =============================================================================
create table if not exists dashboard_summary_cache (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    summary_json jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    expires_at timestamptz not null default (now() + interval '5 minutes'),
    unique (workspace_id)
);

create index if not exists dashboard_summary_cache_workspace_idx on dashboard_summary_cache(workspace_id);

alter table dashboard_summary_cache enable row level security;

create policy dashboard_summary_cache_select_workspace_members on dashboard_summary_cache for select
    using (public.current_user_is_workspace_member(workspace_id));
create policy dashboard_summary_cache_insert_workspace_operators on dashboard_summary_cache for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy dashboard_summary_cache_update_workspace_operators on dashboard_summary_cache for update
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

comment on table dashboard_summary_cache is 'Cached dashboard summary for fast refresh recovery. Refreshed on upload/import/run activity.';