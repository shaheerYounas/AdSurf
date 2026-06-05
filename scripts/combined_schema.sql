-- =============================================================================
-- AdSurf Combined Schema (Local PostgreSQL Migration)
-- Generated from 23 Supabase migrations, stripped of RLS and auth functions.
-- =============================================================================

BEGIN;

-- =============================================================================
-- Extensions
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- Enums (migration 001)
-- =============================================================================
CREATE TYPE workspace_role AS ENUM ('owner', 'admin', 'analyst', 'approver', 'viewer');
CREATE TYPE workspace_status AS ENUM ('active', 'archived');
CREATE TYPE workspace_member_status AS ENUM ('active', 'invited', 'disabled');
CREATE TYPE product_profile_status AS ENUM ('active', 'archived');
CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled');
CREATE TYPE outbox_status AS ENUM ('pending', 'published', 'failed');

-- =============================================================================
-- Core tables (migration 001)
-- =============================================================================
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'seller',
    status workspace_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workspace_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL,
    role workspace_role NOT NULL,
    status workspace_member_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, user_id)
);

CREATE TABLE product_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_name TEXT NOT NULL,
    asin TEXT NULL CHECK (asin IS NULL OR asin ~ '^[A-Z0-9]{10}$'),
    sku TEXT NULL,
    marketplace TEXT NOT NULL DEFAULT 'US',
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    target_acos NUMERIC(8,4) NOT NULL DEFAULT 0.5000 CHECK (target_acos > 0 AND target_acos <= 1),
    default_budget NUMERIC(12,4) NOT NULL DEFAULT 10.0000 CHECK (default_budget > 0),
    default_bid NUMERIC(12,4) NOT NULL DEFAULT 1.0000 CHECK (default_bid > 0),
    status product_profile_status NOT NULL DEFAULT 'active',
    created_by UUID NULL,
    updated_by UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    actor_user_id UUID NULL,
    event_type TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id UUID NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rule_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_set TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    active_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    active_to TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rule_set, version)
);

CREATE TABLE job_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    job_type TEXT NOT NULL,
    status job_status NOT NULL DEFAULT 'queued',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_at TIMESTAMPTZ NULL,
    locked_by TEXT NULL,
    heartbeat_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, job_type, idempotency_key)
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status outbox_status NOT NULL DEFAULT 'pending',
    published_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Core indexes (migration 001)
CREATE INDEX idx_workspace_members_workspace_id ON workspace_members(workspace_id);
CREATE INDEX idx_workspace_members_user_id ON workspace_members(user_id);
CREATE INDEX idx_product_profiles_workspace_id ON product_profiles(workspace_id);
CREATE INDEX idx_product_profiles_status ON product_profiles(status);
CREATE INDEX idx_audit_logs_workspace_id_created_at ON audit_logs(workspace_id, created_at DESC);
CREATE INDEX idx_rule_versions_rule_set ON rule_versions(rule_set);
CREATE INDEX idx_job_queue_status_locked_at ON job_queue(status, locked_at);
CREATE INDEX idx_job_queue_workspace_id ON job_queue(workspace_id);
CREATE INDEX idx_outbox_events_status_created_at ON outbox_events(status, created_at);

-- =============================================================================
-- Uploads (migration 003)
-- =============================================================================
CREATE TYPE upload_status AS ENUM (
    'initialized',
    'uploaded',
    'queued_for_processing',
    'processing',
    'processed',
    'failed',
    'cancelled'
);

CREATE TYPE upload_source_type AS ENUM (
    'competitor_keyword_research'
);

CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL REFERENCES product_profiles(id) ON DELETE RESTRICT,
    uploaded_by UUID,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    file_size_bytes BIGINT CHECK (file_size_bytes IS NULL OR file_size_bytes > 0),
    status upload_status NOT NULL DEFAULT 'initialized',
    source_type upload_source_type NOT NULL,
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    UNIQUE (workspace_id, idempotency_key)
);

CREATE INDEX uploads_workspace_id_idx ON uploads(workspace_id);
CREATE INDEX uploads_product_id_idx ON uploads(product_id);
CREATE INDEX uploads_status_idx ON uploads(status);
CREATE INDEX uploads_created_at_idx ON uploads(created_at);
CREATE INDEX uploads_idempotency_key_idx ON uploads(idempotency_key);

COMMENT ON TABLE uploads IS 'Raw upload metadata only. File parsing and column mapping are intentionally deferred.';

-- =============================================================================
-- Upload Integrity Hardening (migration 004)
-- =============================================================================
ALTER TABLE product_profiles
    ADD CONSTRAINT product_profiles_id_workspace_id_key UNIQUE (id, workspace_id);

ALTER TABLE uploads
    DROP CONSTRAINT uploads_product_id_fkey;

ALTER TABLE uploads
    ADD CONSTRAINT uploads_product_workspace_fk
    FOREIGN KEY (product_id, workspace_id)
    REFERENCES product_profiles(id, workspace_id)
    ON DELETE RESTRICT;

COMMENT ON CONSTRAINT uploads_product_workspace_fk ON uploads IS
    'Prevents upload metadata from referencing a product owned by a different workspace.';

-- =============================================================================
-- Upload Parse (migration 005)
-- =============================================================================
CREATE TYPE upload_parse_status AS ENUM (
    'running',
    'succeeded',
    'failed'
);

ALTER TABLE uploads
    ADD CONSTRAINT uploads_workspace_product_id_key UNIQUE (workspace_id, product_id, id);

CREATE TABLE upload_parse_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    job_id UUID NOT NULL UNIQUE REFERENCES job_queue(id) ON DELETE RESTRICT,
    status upload_parse_status NOT NULL,
    parser_version TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    detected_file_type TEXT NOT NULL,
    detected_sheet_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_sheet_name TEXT,
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    total_columns INTEGER NOT NULL DEFAULT 0 CHECK (total_columns >= 0),
    parsed_rows_count INTEGER NOT NULL DEFAULT 0 CHECK (parsed_rows_count >= 0),
    error_rows_count INTEGER NOT NULL DEFAULT 0 CHECK (error_rows_count >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_message TEXT,
    CONSTRAINT upload_parse_runs_scope_identity_key UNIQUE (id, workspace_id, product_id, upload_id),
    CONSTRAINT upload_parse_runs_upload_fk
        FOREIGN KEY (workspace_id, product_id, upload_id)
        REFERENCES uploads(workspace_id, product_id, id)
        ON DELETE RESTRICT
);

CREATE TABLE upload_parsed_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL REFERENCES upload_parse_runs(id) ON DELETE RESTRICT,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    row_data_json JSONB NOT NULL,
    row_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (parse_run_id, row_number),
    CONSTRAINT upload_parsed_rows_parse_run_scope_fk
        FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id)
        REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id)
        ON DELETE RESTRICT,
    CONSTRAINT upload_parsed_rows_upload_fk
        FOREIGN KEY (workspace_id, product_id, upload_id)
        REFERENCES uploads(workspace_id, product_id, id)
        ON DELETE RESTRICT
);

CREATE TABLE upload_parse_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL REFERENCES upload_parse_runs(id) ON DELETE RESTRICT,
    row_number INTEGER CHECK (row_number IS NULL OR row_number > 0),
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    raw_value_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT upload_parse_errors_parse_run_scope_fk
        FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id)
        REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id)
        ON DELETE RESTRICT,
    CONSTRAINT upload_parse_errors_upload_fk
        FOREIGN KEY (workspace_id, product_id, upload_id)
        REFERENCES uploads(workspace_id, product_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX upload_parse_runs_workspace_upload_idx ON upload_parse_runs(workspace_id, upload_id, created_at DESC);
CREATE INDEX upload_parsed_rows_parse_run_idx ON upload_parsed_rows(parse_run_id, row_number);
CREATE INDEX upload_parse_errors_parse_run_idx ON upload_parse_errors(parse_run_id, row_number);

COMMENT ON TABLE upload_parse_runs IS 'Metadata for deterministic file parsing only.';
COMMENT ON TABLE upload_parsed_rows IS 'Parsed spreadsheet/CSV rows stored as untrusted JSON data.';
COMMENT ON TABLE upload_parse_errors IS 'Row-level or file-level parse errors captured without interpreting spreadsheet content.';

-- =============================================================================
-- Column Mapping (migration 006)
-- =============================================================================
CREATE TYPE upload_column_profile_status AS ENUM (
    'generated',
    'failed'
);

CREATE TYPE upload_column_inferred_data_type AS ENUM (
    'text',
    'integer',
    'decimal',
    'date',
    'boolean',
    'unknown'
);

CREATE TYPE upload_column_mapping_status AS ENUM (
    'draft',
    'valid',
    'invalid',
    'approved',
    'superseded'
);

CREATE TYPE upload_column_mapping_type AS ENUM (
    'manual'
);

CREATE TABLE upload_column_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL,
    status upload_column_profile_status NOT NULL,
    total_columns INTEGER NOT NULL DEFAULT 0 CHECK (total_columns >= 0),
    total_rows_sampled INTEGER NOT NULL DEFAULT 0 CHECK (total_rows_sampled >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (parse_run_id),
    CONSTRAINT upload_column_profiles_scope_identity_key
        UNIQUE (id, workspace_id, product_id, upload_id, parse_run_id),
    CONSTRAINT upload_column_profiles_parse_run_scope_fk
        FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id)
        REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id)
        ON DELETE RESTRICT
);

CREATE TABLE upload_column_profile_columns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL,
    column_profile_id UUID NOT NULL,
    original_column_name TEXT NOT NULL,
    normalized_column_name TEXT NOT NULL,
    column_index INTEGER NOT NULL CHECK (column_index >= 0),
    non_null_count INTEGER NOT NULL DEFAULT 0 CHECK (non_null_count >= 0),
    sample_values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    inferred_data_type upload_column_inferred_data_type NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (column_profile_id, column_index),
    UNIQUE (column_profile_id, original_column_name),
    CONSTRAINT upload_column_profile_columns_profile_scope_fk
        FOREIGN KEY (column_profile_id, workspace_id, product_id, upload_id, parse_run_id)
        REFERENCES upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id)
        ON DELETE RESTRICT
);

CREATE TABLE upload_column_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL,
    column_profile_id UUID NOT NULL,
    status upload_column_mapping_status NOT NULL,
    mapping_version INTEGER NOT NULL CHECK (mapping_version > 0),
    mapping_type upload_column_mapping_type NOT NULL DEFAULT 'manual',
    mapping_json JSONB NOT NULL,
    validation_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    UNIQUE (column_profile_id, mapping_version),
    CONSTRAINT upload_column_mappings_profile_scope_fk
        FOREIGN KEY (column_profile_id, workspace_id, product_id, upload_id, parse_run_id)
        REFERENCES upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id)
        ON DELETE RESTRICT
);

CREATE INDEX upload_column_profiles_workspace_upload_idx
    ON upload_column_profiles(workspace_id, upload_id, created_at DESC);
CREATE INDEX upload_column_profile_columns_profile_idx
    ON upload_column_profile_columns(column_profile_id, column_index);
CREATE INDEX upload_column_mappings_profile_idx
    ON upload_column_mappings(column_profile_id, mapping_version DESC);
CREATE INDEX upload_column_mappings_workspace_upload_idx
    ON upload_column_mappings(workspace_id, upload_id, created_at DESC);

COMMENT ON TABLE upload_column_profiles IS 'Deterministic parsed-column discovery only.';
COMMENT ON TABLE upload_column_profile_columns IS 'Column names, samples, and inferred data types for manual mapping.';
COMMENT ON TABLE upload_column_mappings IS 'Manual column mapping snapshots for later scoring.';

-- =============================================================================
-- Keyword Scoring (migration 007)
-- =============================================================================
CREATE TYPE keyword_scoring_run_status AS ENUM (
    'running',
    'succeeded',
    'failed'
);

CREATE TYPE keyword_candidate_status AS ENUM (
    'approved',
    'rejected',
    'error'
);

ALTER TABLE upload_column_mappings
    ADD CONSTRAINT upload_column_mappings_scope_identity_key
    UNIQUE (id, workspace_id, product_id, upload_id, parse_run_id);

CREATE TABLE keyword_scoring_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    parse_run_id UUID NOT NULL,
    column_mapping_id UUID NOT NULL,
    status keyword_scoring_run_status NOT NULL,
    scoring_version INTEGER NOT NULL,
    rule_version_id UUID NULL REFERENCES rule_versions(id),
    idempotency_key TEXT NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    scored_rows INTEGER NOT NULL DEFAULT 0 CHECK (scored_rows >= 0),
    approved_count INTEGER NOT NULL DEFAULT 0 CHECK (approved_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_message TEXT NULL,
    UNIQUE (column_mapping_id, scoring_version),
    UNIQUE (workspace_id, idempotency_key),
    CONSTRAINT keyword_scoring_runs_mapping_scope_fk
        FOREIGN KEY (column_mapping_id, workspace_id, product_id, upload_id, parse_run_id)
        REFERENCES upload_column_mappings(id, workspace_id, product_id, upload_id, parse_run_id),
    CONSTRAINT keyword_scoring_runs_scope_identity_key
        UNIQUE (id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)
);

CREATE TABLE keyword_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    parse_run_id UUID NOT NULL,
    column_mapping_id UUID NOT NULL,
    scoring_run_id UUID NOT NULL,
    source_row_id UUID NOT NULL,
    search_term TEXT NULL,
    search_volume NUMERIC NULL,
    competitor_rank_values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    relevance_score INTEGER NULL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 10),
    scoring_status keyword_candidate_status NOT NULL,
    rejection_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT keyword_candidates_scoring_run_scope_fk
        FOREIGN KEY (scoring_run_id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)
        REFERENCES keyword_scoring_runs(id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)
        ON DELETE CASCADE,
    CONSTRAINT keyword_candidates_search_term_required_for_scored
        CHECK (scoring_status = 'error' OR NULLIF(BTRIM(search_term), '') IS NOT NULL)
);

CREATE INDEX keyword_scoring_runs_workspace_upload_idx
    ON keyword_scoring_runs(workspace_id, upload_id, created_at DESC);
CREATE INDEX keyword_candidates_workspace_product_idx
    ON keyword_candidates(workspace_id, product_id);
CREATE INDEX keyword_candidates_upload_idx
    ON keyword_candidates(upload_id);
CREATE INDEX keyword_candidates_scoring_run_idx
    ON keyword_candidates(scoring_run_id);
CREATE INDEX keyword_candidates_scoring_status_idx
    ON keyword_candidates(scoring_status);
CREATE INDEX keyword_candidates_relevance_score_idx
    ON keyword_candidates(relevance_score);
CREATE INDEX keyword_candidates_search_term_idx
    ON keyword_candidates(search_term);

COMMENT ON TABLE keyword_scoring_runs IS 'Deterministic keyword relevance scoring runs.';
COMMENT ON TABLE keyword_candidates IS 'Row-level keyword relevance outcomes from approved manual column mappings.';

-- =============================================================================
-- Keyword Review (migration 008)
-- =============================================================================
CREATE TYPE keyword_candidate_override_action AS ENUM ('approve', 'reject');
CREATE TYPE reviewed_keyword_status AS ENUM ('approved', 'rejected');
CREATE TYPE approved_keyword_set_status AS ENUM ('created', 'locked', 'superseded');

ALTER TABLE keyword_candidates
    ADD CONSTRAINT keyword_candidates_review_scope_identity_key
    UNIQUE (id, workspace_id, product_id, scoring_run_id);

ALTER TABLE keyword_scoring_runs
    ADD CONSTRAINT keyword_scoring_runs_review_scope_identity_key
    UNIQUE (id, workspace_id, product_id, column_mapping_id);

CREATE TABLE keyword_candidate_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL,
    scoring_run_id UUID NOT NULL,
    keyword_candidate_id UUID NOT NULL,
    override_action keyword_candidate_override_action NOT NULL,
    original_scoring_status keyword_candidate_status NOT NULL CHECK (original_scoring_status IN ('approved', 'rejected')),
    new_status reviewed_keyword_status NOT NULL,
    reason TEXT NOT NULL CHECK (LENGTH(BTRIM(reason)) > 0),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT keyword_candidate_overrides_candidate_scope_fk
        FOREIGN KEY (keyword_candidate_id, workspace_id, product_id, scoring_run_id)
        REFERENCES keyword_candidates(id, workspace_id, product_id, scoring_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT keyword_candidate_overrides_action_status_check
        CHECK (
            (override_action = 'approve' AND new_status = 'approved')
            OR (override_action = 'reject' AND new_status = 'rejected')
        ),
    UNIQUE (keyword_candidate_id)
);

CREATE TABLE approved_keyword_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL,
    scoring_run_id UUID NOT NULL,
    column_mapping_id UUID NOT NULL,
    name TEXT NOT NULL CHECK (LENGTH(BTRIM(name)) > 0),
    status approved_keyword_set_status NOT NULL DEFAULT 'locked',
    keyword_count INTEGER NOT NULL DEFAULT 0 CHECK (keyword_count >= 0),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    CONSTRAINT approved_keyword_sets_scoring_run_scope_fk
        FOREIGN KEY (scoring_run_id, workspace_id, product_id, column_mapping_id)
        REFERENCES keyword_scoring_runs(id, workspace_id, product_id, column_mapping_id)
        ON DELETE RESTRICT,
    CONSTRAINT approved_keyword_sets_scope_identity_key
        UNIQUE (id, workspace_id, product_id)
);

CREATE TABLE approved_keyword_set_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL,
    approved_keyword_set_id UUID NOT NULL,
    scoring_run_id UUID NOT NULL,
    keyword_candidate_id UUID NOT NULL,
    search_term TEXT NOT NULL CHECK (LENGTH(BTRIM(search_term)) > 0),
    search_volume NUMERIC(18,4),
    relevance_score INTEGER NOT NULL CHECK (relevance_score BETWEEN 0 AND 10),
    source_status keyword_candidate_status NOT NULL,
    final_status reviewed_keyword_status NOT NULL DEFAULT 'approved' CHECK (final_status = 'approved'),
    override_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT approved_keyword_set_items_set_scope_fk
        FOREIGN KEY (approved_keyword_set_id, workspace_id, product_id)
        REFERENCES approved_keyword_sets(id, workspace_id, product_id)
        ON DELETE RESTRICT,
    CONSTRAINT approved_keyword_set_items_candidate_scope_fk
        FOREIGN KEY (keyword_candidate_id, workspace_id, product_id, scoring_run_id)
        REFERENCES keyword_candidates(id, workspace_id, product_id, scoring_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT approved_keyword_set_items_override_fk
        FOREIGN KEY (override_id)
        REFERENCES keyword_candidate_overrides(id)
        ON DELETE RESTRICT,
    UNIQUE (approved_keyword_set_id, keyword_candidate_id)
);

CREATE INDEX keyword_candidate_overrides_workspace_product_idx ON keyword_candidate_overrides(workspace_id, product_id);
CREATE INDEX keyword_candidate_overrides_scoring_run_idx ON keyword_candidate_overrides(scoring_run_id);
CREATE INDEX approved_keyword_sets_workspace_product_idx ON approved_keyword_sets(workspace_id, product_id);
CREATE INDEX approved_keyword_sets_scoring_run_idx ON approved_keyword_sets(scoring_run_id);
CREATE INDEX approved_keyword_set_items_set_idx ON approved_keyword_set_items(approved_keyword_set_id);
CREATE INDEX approved_keyword_set_items_scoring_run_idx ON approved_keyword_set_items(scoring_run_id);
CREATE INDEX approved_keyword_set_items_search_term_idx ON approved_keyword_set_items(search_term);

-- =============================================================================
-- Campaign Export (migration 009)
-- =============================================================================
CREATE TABLE campaign_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL,
    approved_keyword_set_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('generated', 'approved', 'rejected', 'superseded')),
    rule_version_id TEXT NOT NULL,
    plan_json JSONB NOT NULL,
    created_by UUID NOT NULL,
    approved_by UUID,
    approval_note TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT campaign_plans_product_fk
        FOREIGN KEY (product_id, workspace_id)
        REFERENCES product_profiles(id, workspace_id)
        ON DELETE RESTRICT,
    CONSTRAINT campaign_plans_keyword_set_fk
        FOREIGN KEY (approved_keyword_set_id, workspace_id, product_id)
        REFERENCES approved_keyword_sets(id, workspace_id, product_id)
        ON DELETE RESTRICT,
    UNIQUE (workspace_id, product_id, version)
);

CREATE TABLE bulk_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    product_id UUID NOT NULL,
    campaign_plan_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'failed')),
    storage_path TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL CHECK (LENGTH(BTRIM(original_filename)) > 0),
    rows_json JSONB NOT NULL,
    approved_by UUID NOT NULL,
    approval_note TEXT NOT NULL CHECK (LENGTH(BTRIM(approval_note)) > 0),
    approved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT bulk_exports_plan_fk
        FOREIGN KEY (campaign_plan_id)
        REFERENCES campaign_plans(id)
        ON DELETE RESTRICT,
    CONSTRAINT bulk_exports_product_fk
        FOREIGN KEY (product_id, workspace_id)
        REFERENCES product_profiles(id, workspace_id)
        ON DELETE RESTRICT
);

CREATE INDEX campaign_plans_workspace_product_idx ON campaign_plans(workspace_id, product_id);
CREATE INDEX campaign_plans_keyword_set_idx ON campaign_plans(approved_keyword_set_id);
CREATE INDEX bulk_exports_workspace_product_idx ON bulk_exports(workspace_id, product_id);
CREATE INDEX bulk_exports_plan_idx ON bulk_exports(campaign_plan_id);

-- =============================================================================
-- Monitoring & Recommendations (migration 010)
-- =============================================================================
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'amazon_ads_sp_search_term_report';

CREATE TYPE monitoring_import_status AS ENUM ('queued', 'processing', 'succeeded', 'failed');
CREATE TYPE recommendation_status AS ENUM ('pending_approval', 'approved', 'rejected', 'superseded');
CREATE TYPE recommendation_type AS ENUM ('increase_bid', 'decrease_bid', 'pause_review', 'negative_keyword_review', 'watch_lock');
CREATE TYPE recommendation_priority AS ENUM ('high', 'medium', 'low');

CREATE TABLE monitoring_imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type = 'sponsored_products_search_term'),
    status monitoring_import_status NOT NULL DEFAULT 'queued',
    date_range_start TEXT,
    date_range_end TEXT,
    total_rows INTEGER NOT NULL DEFAULT 0,
    processed_rows INTEGER NOT NULL DEFAULT 0,
    error_rows INTEGER NOT NULL DEFAULT 0,
    data_quality_warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by UUID NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, product_id, upload_id, report_type),
    CONSTRAINT monitoring_imports_product_fk
        FOREIGN KEY (product_id, workspace_id)
        REFERENCES product_profiles(id, workspace_id)
        ON DELETE RESTRICT,
    CONSTRAINT monitoring_imports_upload_fk
        FOREIGN KEY (workspace_id, product_id, upload_id)
        REFERENCES uploads(workspace_id, product_id, id)
        ON DELETE RESTRICT,
    CONSTRAINT monitoring_imports_parse_run_fk
        FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id)
        REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id)
        ON DELETE RESTRICT
);

CREATE TABLE monitoring_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL,
    monitoring_import_id UUID NOT NULL,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL,
    source_row_id UUID NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    targeting TEXT NOT NULL,
    match_type TEXT,
    customer_search_term TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    spend NUMERIC(12,4) NOT NULL DEFAULT 0,
    sales NUMERIC(12,4) NOT NULL DEFAULT 0,
    orders INTEGER NOT NULL DEFAULT 0,
    units INTEGER,
    cpc NUMERIC(12,4),
    ctr NUMERIC(8,4),
    cvr NUMERIC(8,4),
    acos NUMERIC(8,4),
    roas NUMERIC(12,4),
    raw_metrics_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT monitoring_snapshots_import_fk
        FOREIGN KEY (monitoring_import_id)
        REFERENCES monitoring_imports(id)
        ON DELETE RESTRICT,
    CONSTRAINT monitoring_snapshots_scope_fk
        FOREIGN KEY (workspace_id, product_id, upload_id)
        REFERENCES uploads(workspace_id, product_id, id)
        ON DELETE RESTRICT,
    CONSTRAINT monitoring_snapshots_source_row_fk
        FOREIGN KEY (source_row_id)
        REFERENCES upload_parsed_rows(id)
        ON DELETE RESTRICT
);

CREATE TABLE recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL,
    monitoring_import_id UUID NOT NULL,
    snapshot_id UUID NOT NULL,
    recommendation_type recommendation_type NOT NULL,
    status recommendation_status NOT NULL DEFAULT 'pending_approval',
    priority recommendation_priority NOT NULL,
    rule_version_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    targeting TEXT NOT NULL,
    customer_search_term TEXT NOT NULL,
    input_metrics_json JSONB NOT NULL,
    proposed_action_json JSONB NOT NULL,
    explanation_json JSONB NOT NULL,
    decided_by UUID,
    decision_note TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT recommendations_product_fk
        FOREIGN KEY (product_id, workspace_id)
        REFERENCES product_profiles(id, workspace_id)
        ON DELETE RESTRICT,
    CONSTRAINT recommendations_import_fk
        FOREIGN KEY (monitoring_import_id)
        REFERENCES monitoring_imports(id)
        ON DELETE RESTRICT,
    CONSTRAINT recommendations_snapshot_fk
        FOREIGN KEY (snapshot_id)
        REFERENCES monitoring_snapshots(id)
        ON DELETE RESTRICT
);

CREATE TABLE recommendation_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    recommendation_id UUID NOT NULL REFERENCES recommendations(id) ON DELETE RESTRICT,
    decision recommendation_status NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor_user_id UUID NOT NULL,
    note TEXT NOT NULL CHECK (LENGTH(BTRIM(note)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_json JSONB NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX monitoring_imports_workspace_product_idx ON monitoring_imports(workspace_id, product_id, created_at DESC);
CREATE INDEX monitoring_imports_upload_report_idx ON monitoring_imports(workspace_id, product_id, upload_id, report_type);
CREATE INDEX monitoring_snapshots_workspace_product_idx ON monitoring_snapshots(workspace_id, product_id);
CREATE INDEX recommendations_workspace_status_idx ON recommendations(workspace_id, status, priority);
CREATE INDEX recommendations_workspace_type_idx ON recommendations(workspace_id, recommendation_type);
CREATE INDEX recommendation_decisions_workspace_idx ON recommendation_decisions(workspace_id, recommendation_id);
CREATE INDEX ai_runs_workspace_agent_idx ON ai_runs(workspace_id, agent_name, created_at DESC);

-- =============================================================================
-- Monitoring Phase 1 Recommendations (migration 011)
-- =============================================================================
ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'keep_running';
ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'add_negative_exact';
ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'add_negative_phrase';
ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'move_to_exact';
ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'data_quality_review';
ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'budget_review';
ALTER TYPE recommendation_priority ADD VALUE IF NOT EXISTS 'critical';
ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'pending';

ALTER TABLE recommendations
    ADD COLUMN IF NOT EXISTS entity_type TEXT NOT NULL DEFAULT 'search_term',
    ADD COLUMN IF NOT EXISTS confidence TEXT NOT NULL DEFAULT 'medium',
    ADD COLUMN IF NOT EXISTS current_metric_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE ai_runs
    ADD COLUMN IF NOT EXISTS product_id UUID;

COMMENT ON COLUMN recommendations.evidence_json IS
    'Deterministic monitoring evidence including rule version, thresholds, search-term metrics, and campaign/ad group/target rollups.';
COMMENT ON COLUMN recommendations.entity_type IS
    'Recommendation entity grain: campaign, ad_group, target, or search_term.';
COMMENT ON COLUMN recommendations.confidence IS
    'Deterministic rule confidence: low, medium, or high.';

-- =============================================================================
-- Dashboard Performance Indexes (migration 012)
-- =============================================================================
CREATE INDEX IF NOT EXISTS product_profiles_workspace_created_desc_idx
    ON product_profiles(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS uploads_workspace_created_desc_idx
    ON uploads(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS uploads_workspace_status_created_desc_idx
    ON uploads(workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS recommendations_workspace_product_status_priority_created_idx
    ON recommendations(workspace_id, product_id, status, priority, created_at DESC);

CREATE INDEX IF NOT EXISTS recommendations_workspace_priority_created_idx
    ON recommendations(workspace_id, priority, created_at DESC);

CREATE INDEX IF NOT EXISTS ai_runs_workspace_product_agent_created_idx
    ON ai_runs(workspace_id, product_id, agent_name, created_at DESC);

-- =============================================================================
-- Agent Control Center (migration 013)
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_definitions (
    agent_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    task_type TEXT NOT NULL,
    enabled_by_default BOOLEAN NOT NULL DEFAULT true,
    allowed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
    output_type TEXT NOT NULL,
    can_be_disabled BOOLEAN NOT NULL DEFAULT true,
    can_be_rerun BOOLEAN NOT NULL DEFAULT true,
    can_be_stopped BOOLEAN NOT NULL DEFAULT true,
    requires_human_approval BOOLEAN NOT NULL DEFAULT true,
    can_mutate_live_amazon_ads BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID,
    agent_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    mode TEXT NOT NULL DEFAULT 'hybrid' CHECK (mode IN ('deterministic', 'ai', 'hybrid')),
    strictness_level TEXT NOT NULL DEFAULT 'balanced' CHECK (strictness_level IN ('conservative', 'balanced', 'aggressive')),
    confidence_threshold TEXT NOT NULL DEFAULT 'medium' CHECK (confidence_threshold IN ('low', 'medium', 'high')),
    max_recommendations INTEGER NOT NULL DEFAULT 100 CHECK (max_recommendations > 0 AND max_recommendations <= 1000),
    allow_bid_recommendations BOOLEAN NOT NULL DEFAULT true,
    allow_negative_keyword_recommendations BOOLEAN NOT NULL DEFAULT true,
    allow_pause_recommendations BOOLEAN NOT NULL DEFAULT true,
    allow_budget_recommendations BOOLEAN NOT NULL DEFAULT true,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id UUID,
    monitoring_import_id UUID REFERENCES monitoring_imports(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_workflow_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    workflow_id UUID REFERENCES agent_workflows(id) ON DELETE CASCADE,
    monitoring_import_id UUID REFERENCES monitoring_imports(id) ON DELETE RESTRICT,
    source_agent_id TEXT NOT NULL,
    target_agent_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting_for_dependency',
    data_passed_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent_run_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL,
    agent_run_id UUID REFERENCES ai_runs(id) ON DELETE SET NULL,
    monitoring_import_id UUID REFERENCES monitoring_imports(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_control_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL,
    agent_run_id UUID REFERENCES ai_runs(id) ON DELETE SET NULL,
    monitoring_import_id UUID REFERENCES monitoring_imports(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    actor_user_id UUID,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE ai_runs
    ADD COLUMN IF NOT EXISTS agent_id TEXT,
    ADD COLUMN IF NOT EXISTS monitoring_import_id UUID,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stopped_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS controlled_by UUID,
    ADD COLUMN IF NOT EXISTS control_reason TEXT,
    ADD COLUMN IF NOT EXISTS input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS dependency_agent_run_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recommendation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS mode TEXT,
    ADD COLUMN IF NOT EXISTS strictness_level TEXT,
    ADD COLUMN IF NOT EXISTS confidence_threshold TEXT;

CREATE INDEX IF NOT EXISTS agent_configs_workspace_idx ON agent_configs(workspace_id, product_id, agent_id);
CREATE UNIQUE INDEX IF NOT EXISTS agent_configs_scope_unique_idx ON agent_configs(workspace_id, COALESCE(product_id, '00000000-0000-0000-0000-000000000000'::uuid), agent_id);
CREATE INDEX IF NOT EXISTS agent_run_events_workspace_import_idx ON agent_run_events(workspace_id, monitoring_import_id, created_at);
CREATE INDEX IF NOT EXISTS agent_run_events_run_idx ON agent_run_events(agent_run_id, created_at);
CREATE INDEX IF NOT EXISTS agent_control_actions_workspace_idx ON agent_control_actions(workspace_id, agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_runs_monitoring_import_idx ON ai_runs(workspace_id, monitoring_import_id, created_at DESC);

COMMENT ON TABLE agent_configs IS 'Workspace/product-level agent controls. Agents cannot mutate live Amazon Ads and cannot bypass human approval.';
COMMENT ON TABLE agent_control_actions IS 'Audited user controls for pausing, stopping, resuming, rerunning, and configuring agents.';
COMMENT ON TABLE agent_run_events IS 'Chronological agent event timeline for Agent Control Center.';

-- Seed agent definitions (migration 013 + 015)
INSERT INTO agent_definitions (
    agent_id, display_name, description, task_type, enabled_by_default, allowed_actions,
    input_dependencies, output_type, can_be_disabled, can_be_rerun, can_be_stopped,
    requires_human_approval, can_mutate_live_amazon_ads
)
VALUES
    ('performance_import_agent', 'Performance Import Agent', 'Validates report quality, missing columns, row count, and data-quality warnings.', 'validation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '[]'::jsonb, 'report_quality_summary', true, true, true, true, false),
    ('metrics_analysis_agent', 'Metrics Analysis Agent', 'Analyzes uploaded Amazon Ads performance metrics and finds winners, wasters, and risks.', 'analysis', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["performance_import_agent"]'::jsonb, 'performance_summary', true, true, true, true, false),
    ('ai_recommendation_brain_agent', 'AI Recommendation Brain', 'Uses DeepSeek or configured fallback mode to generate recommendation decisions from normalized report evidence.', 'decision', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["metrics_analysis_agent"]'::jsonb, 'recommendation_json', true, true, true, true, false),
    ('bid_optimization_agent', 'Bid Optimization Agent', 'Reviews bid-related recommendations and explains increase, decrease, watch-lock, and bid risk logic.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'bid_recommendation_explanations', true, true, true, true, false),
    ('negative_keyword_agent', 'Negative Keyword Agent', 'Reviews wasted search terms and explains negative exact or phrase evidence.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'negative_keyword_explanations', true, true, true, true, false),
    ('pause_review_agent', 'Pause Review Agent', 'Reviews campaigns, ad groups, targets, or search terms that may need pause review.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'pause_review_explanations', true, true, true, true, false),
    ('stakeholder_reporting_agent', 'Stakeholder Reporting Agent', 'Creates dashboard summaries, executive summary, next-best actions, and approver notes.', 'reporting', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["bid_optimization_agent","negative_keyword_agent","pause_review_agent"]'::jsonb, 'dashboard_summary', true, true, true, true, false),
    ('report_upload_node', 'Report Upload', 'Receives Amazon Ads reports or bulk sheets and starts the account import workflow.', 'start', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '[]'::jsonb, 'uploaded_report', false, true, true, true, false),
    ('report_detection_agent', 'Report Detection Agent', 'Classifies the uploaded report type, required columns, confidence, and available entity levels.', 'validation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["report_upload_node"]'::jsonb, 'report_detection_summary', true, true, true, true, false),
    ('product_resolution_agent', 'Product Resolution Agent', 'Detects ASINs, SKUs, product names, and mapping suggestions before account-level analysis.', 'mapping', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["report_detection_agent"]'::jsonb, 'product_mapping_suggestions', true, true, true, true, false),
    ('budget_allocation_agent', 'Budget Allocation Agent', 'Reviews campaign and product budget pressure and suggests approval-gated budget review actions.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'budget_recommendation_explanations', true, true, true, true, false),
    ('human_approval_agent', 'Human Approval Agent', 'Routes recommendations to the approval queue and prevents automatic approval or live ad mutation.', 'approval', true, '["view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["stakeholder_reporting_agent"]'::jsonb, 'approval_queue', false, false, false, true, false)
ON CONFLICT (agent_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    task_type = EXCLUDED.task_type,
    enabled_by_default = EXCLUDED.enabled_by_default,
    allowed_actions = EXCLUDED.allowed_actions,
    input_dependencies = EXCLUDED.input_dependencies,
    output_type = EXCLUDED.output_type,
    can_be_disabled = EXCLUDED.can_be_disabled,
    can_be_rerun = EXCLUDED.can_be_rerun,
    can_be_stopped = EXCLUDED.can_be_stopped,
    requires_human_approval = EXCLUDED.requires_human_approval,
    can_mutate_live_amazon_ads = EXCLUDED.can_mutate_live_amazon_ads,
    updated_at = now();

-- =============================================================================
-- Account Bulk Imports (migration 014)
-- =============================================================================
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'single_product_report';
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'account_bulk_report';
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'sponsored_products_search_term_report';
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'sponsored_products_targeting_report';
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'sponsored_products_campaign_report';
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'bulk_sheet';
ALTER TYPE upload_source_type ADD VALUE IF NOT EXISTS 'unknown_report';

ALTER TABLE uploads ALTER COLUMN product_id DROP NOT NULL;
ALTER TABLE upload_parse_runs ALTER COLUMN product_id DROP NOT NULL;
ALTER TABLE upload_parsed_rows ALTER COLUMN product_id DROP NOT NULL;
ALTER TABLE upload_parse_errors ALTER COLUMN product_id DROP NOT NULL;

ALTER TABLE uploads ADD CONSTRAINT uploads_workspace_id_id_key UNIQUE (workspace_id, id);
ALTER TABLE upload_parse_runs ADD CONSTRAINT upload_parse_runs_workspace_id_id_key UNIQUE (workspace_id, id);

CREATE TABLE IF NOT EXISTS account_imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    upload_id UUID NOT NULL,
    parse_run_id UUID NOT NULL,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'detected' CHECK (status IN ('detected', 'needs_mapping', 'ready_for_analysis', 'processing', 'succeeded', 'failed')),
    detected_report_type TEXT NOT NULL CHECK (detected_report_type IN (
        'single_product_report',
        'account_bulk_report',
        'sponsored_products_search_term_report',
        'sponsored_products_targeting_report',
        'sponsored_products_campaign_report',
        'bulk_sheet',
        'unknown_report'
    )),
    detection_confidence TEXT NOT NULL CHECK (detection_confidence IN ('high', 'medium', 'low')),
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    processed_rows INTEGER NOT NULL DEFAULT 0 CHECK (processed_rows >= 0),
    error_rows INTEGER NOT NULL DEFAULT 0 CHECK (error_rows >= 0),
    data_quality_warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by UUID,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_imports_upload_fk
        FOREIGN KEY (workspace_id, upload_id)
        REFERENCES uploads(workspace_id, id)
        ON DELETE RESTRICT,
    CONSTRAINT account_imports_parse_run_fk
        FOREIGN KEY (workspace_id, parse_run_id)
        REFERENCES upload_parse_runs(workspace_id, id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_import_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    account_import_id UUID NOT NULL REFERENCES account_imports(id) ON DELETE RESTRICT,
    product_id UUID,
    asin TEXT,
    sku TEXT,
    product_name TEXT,
    campaign_name TEXT,
    ad_group_name TEXT,
    targeting TEXT,
    customer_search_term TEXT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('account', 'product', 'campaign', 'ad_group', 'target', 'search_term')),
    entity_key TEXT NOT NULL,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('matched_existing_product', 'suggested_new_product', 'unknown_product', 'needs_user_mapping')),
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_row_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_import_entities_product_fk
        FOREIGN KEY (product_id, workspace_id)
        REFERENCES product_profiles(id, workspace_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS product_mapping_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    account_import_id UUID NOT NULL REFERENCES account_imports(id) ON DELETE RESTRICT,
    asin TEXT,
    sku TEXT,
    detected_product_name TEXT,
    suggested_product_id UUID,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'manually_mapped')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT product_mapping_suggestions_product_fk
        FOREIGN KEY (suggested_product_id, workspace_id)
        REFERENCES product_profiles(id, workspace_id)
        ON DELETE RESTRICT
);

ALTER TABLE recommendations
    ALTER COLUMN product_id DROP NOT NULL,
    ALTER COLUMN monitoring_import_id DROP NOT NULL,
    ALTER COLUMN snapshot_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS account_import_id UUID REFERENCES account_imports(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS entity_type TEXT CHECK (entity_type IN ('account', 'product', 'campaign', 'ad_group', 'target', 'search_term')),
    ADD COLUMN IF NOT EXISTS entity_key TEXT,
    ADD COLUMN IF NOT EXISTS decision_source TEXT,
    ADD COLUMN IF NOT EXISTS agent_run_id UUID REFERENCES ai_runs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS ai_run_id UUID REFERENCES ai_runs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approval_boundary JSONB NOT NULL DEFAULT '{"requires_human_approval": true, "executes_live_amazon_change": false}'::jsonb;

ALTER TABLE agent_configs
    ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'deepseek',
    ADD COLUMN IF NOT EXISTS model TEXT,
    ADD COLUMN IF NOT EXISTS max_rows_per_ai_call INTEGER NOT NULL DEFAULT 500 CHECK (max_rows_per_ai_call > 0),
    ADD COLUMN IF NOT EXISTS max_products_per_run INTEGER NOT NULL DEFAULT 50 CHECK (max_products_per_run > 0),
    ADD COLUMN IF NOT EXISTS max_groups_per_ai_call INTEGER NOT NULL DEFAULT 100 CHECK (max_groups_per_ai_call > 0),
    ADD COLUMN IF NOT EXISTS analysis_depth TEXT NOT NULL DEFAULT 'standard' CHECK (analysis_depth IN ('quick', 'standard', 'deep')),
    ADD COLUMN IF NOT EXISTS include_account_level_analysis BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS include_product_level_analysis BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS include_campaign_level_analysis BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS include_keyword_level_analysis BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS include_search_term_level_analysis BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_keep_running BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_increase_bid BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_decrease_bid BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_pause_review BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_negative_exact BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_negative_phrase BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_move_to_exact BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_budget_review BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_data_quality_review BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS allow_product_mapping_recommendations BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS max_bid_increase_multiplier NUMERIC(6,4) NOT NULL DEFAULT 1.1000,
    ADD COLUMN IF NOT EXISTS max_bid_decrease_multiplier NUMERIC(6,4) NOT NULL DEFAULT 0.9000,
    ADD COLUMN IF NOT EXISTS require_high_confidence_for_pause BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS require_high_confidence_for_negative_keywords BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS require_min_clicks_before_action INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN IF NOT EXISTS require_min_spend_before_action NUMERIC(12,4) NOT NULL DEFAULT 10.0000,
    ADD COLUMN IF NOT EXISTS target_acos_override NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS min_orders_for_scaling INTEGER NOT NULL DEFAULT 2,
    ADD COLUMN IF NOT EXISTS min_roas_for_scaling NUMERIC(8,4) NOT NULL DEFAULT 2.0000,
    ADD COLUMN IF NOT EXISTS custom_system_instruction TEXT,
    ADD COLUMN IF NOT EXISTS custom_business_goal TEXT,
    ADD COLUMN IF NOT EXISTS optimization_goal TEXT NOT NULL DEFAULT 'conservative_profitability',
    ADD COLUMN IF NOT EXISTS brand_safety_notes TEXT,
    ADD COLUMN IF NOT EXISTS competitor_notes TEXT,
    ADD COLUMN IF NOT EXISTS product_margin_notes TEXT,
    ADD COLUMN IF NOT EXISTS recommendation_language TEXT NOT NULL DEFAULT 'en',
    ADD COLUMN IF NOT EXISTS explanation_detail TEXT NOT NULL DEFAULT 'normal' CHECK (explanation_detail IN ('simple', 'normal', 'expert')),
    ADD COLUMN IF NOT EXISTS show_raw_ai_reasoning_summary BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS show_metric_evidence BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS require_action_risk_note BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS chunk_strategy TEXT NOT NULL DEFAULT 'by_product' CHECK (chunk_strategy IN ('by_product', 'by_campaign', 'by_entity_priority'));

CREATE INDEX IF NOT EXISTS account_imports_workspace_idx ON account_imports(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS account_imports_upload_idx ON account_imports(workspace_id, upload_id);
CREATE INDEX IF NOT EXISTS account_import_entities_import_idx ON account_import_entities(workspace_id, account_import_id, entity_type);
CREATE INDEX IF NOT EXISTS account_import_entities_product_idx ON account_import_entities(workspace_id, product_id);
CREATE INDEX IF NOT EXISTS account_import_entities_campaign_idx ON account_import_entities(workspace_id, campaign_name);
CREATE INDEX IF NOT EXISTS product_mapping_suggestions_import_idx ON product_mapping_suggestions(workspace_id, account_import_id, status);
CREATE INDEX IF NOT EXISTS recommendations_account_import_idx ON recommendations(workspace_id, account_import_id, entity_type);

COMMENT ON TABLE account_imports IS 'Account-level Amazon Ads report or bulk sheet imports.';
COMMENT ON TABLE account_import_entities IS 'Deterministic grouping of account import rows by product, campaign, ad group, target, and search term.';
COMMENT ON TABLE product_mapping_suggestions IS 'Pending product mapping suggestions generated from uploaded ASIN, SKU, or product-name evidence.';

-- =============================================================================
-- LangGraph Orchestration Foundation (migration 016)
-- =============================================================================
ALTER TABLE agent_workflows
    ADD COLUMN IF NOT EXISTS account_import_id UUID REFERENCES account_imports(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES uploads(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS workflow_type TEXT NOT NULL DEFAULT 'account_import_analysis',
    ADD COLUMN IF NOT EXISTS current_node TEXT,
    ADD COLUMN IF NOT EXISTS state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_by UUID,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS agent_workflow_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_workflow_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT,
    node_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms INTEGER,
    provider TEXT,
    model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    agent_id TEXT,
    tool_name TEXT NOT NULL,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'succeeded',
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_llm_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    input_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd NUMERIC(12,6),
    latency_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'succeeded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS human_approval_gates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    gate_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'approved', 'rejected', 'edited')),
    requested_action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    approver_user_id UUID,
    decision_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS agent_workflows_workspace_account_import_idx ON agent_workflows(workspace_id, account_import_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_workflows_workspace_upload_idx ON agent_workflows(workspace_id, upload_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_workflow_checkpoints_workflow_idx ON agent_workflow_checkpoints(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS agent_workflow_events_workflow_idx ON agent_workflow_events(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS agent_workflow_events_workspace_idx ON agent_workflow_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_tool_calls_workflow_idx ON agent_tool_calls(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS agent_llm_calls_workflow_idx ON agent_llm_calls(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS human_approval_gates_workspace_status_idx ON human_approval_gates(workspace_id, status, created_at DESC);

COMMENT ON TABLE agent_workflow_events IS 'Durable agent workflow trace events. Agents create recommendations only and cannot execute live Amazon Ads changes.';
COMMENT ON TABLE human_approval_gates IS 'Approval gates for workflow recommendations. Approval decisions are audited and do not mutate live Amazon Ads.';

-- =============================================================================
-- Competitor Cleaned Data (migration 017)
-- =============================================================================
CREATE TYPE competitor_cleaned_data_status AS ENUM (
    'queued',
    'processing',
    'succeeded',
    'failed'
);

CREATE TABLE competitor_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID REFERENCES product_profiles(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL CHECK (LENGTH(BTRIM(original_filename)) > 0),
    storage_path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL CHECK (LENGTH(BTRIM(mime_type)) > 0),
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes > 0),
    status competitor_cleaned_data_status NOT NULL DEFAULT 'queued',
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    cleaned_column_count INTEGER NOT NULL DEFAULT 0 CHECK (cleaned_column_count >= 0),
    detected_columns_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT NULL,
    uploaded_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, workspace_id)
);

CREATE TABLE competitor_cleaned_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    competitor_upload_id UUID NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    search_term TEXT NULL,
    search_volume NUMERIC NULL,
    competitor_rank_values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_metrics_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT competitor_cleaned_rows_upload_fk
        FOREIGN KEY (competitor_upload_id, workspace_id)
        REFERENCES competitor_uploads(id, workspace_id)
        ON DELETE CASCADE,
    UNIQUE (workspace_id, competitor_upload_id, row_number)
);

CREATE INDEX competitor_uploads_workspace_idx
    ON competitor_uploads(workspace_id, created_at DESC);

CREATE INDEX competitor_uploads_product_idx
    ON competitor_uploads(product_id);

CREATE INDEX competitor_cleaned_rows_upload_idx
    ON competitor_cleaned_rows(competitor_upload_id);

CREATE INDEX competitor_cleaned_rows_search_term_idx
    ON competitor_cleaned_rows(search_term);

COMMENT ON TABLE competitor_uploads IS 'Phase 1 competitor research file uploads before scoring.';
COMMENT ON TABLE competitor_cleaned_rows IS 'Extracted search terms with only search volume and competitor organic rank values.';

-- =============================================================================
-- Competitor Relevance Scoring (migration 018)
-- =============================================================================
ALTER TABLE competitor_cleaned_rows
    ADD COLUMN relevance_score INTEGER NULL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 10),
    ADD COLUMN scoring_status TEXT NULL CHECK (scoring_status IN ('approved', 'rejected', 'error')),
    ADD COLUMN rejection_reason TEXT NULL,
    ADD COLUMN scored_at TIMESTAMPTZ NULL;

CREATE INDEX competitor_cleaned_rows_relevance_score_idx
    ON competitor_cleaned_rows(relevance_score);

CREATE INDEX competitor_cleaned_rows_scoring_status_idx
    ON competitor_cleaned_rows(scoring_status);

COMMENT ON COLUMN competitor_cleaned_rows.relevance_score IS 'Relevance score from 0-10. One point per competitor with organic rank < 15.';
COMMENT ON COLUMN competitor_cleaned_rows.scoring_status IS 'approved (score >= 3), rejected (score 0-2), or error.';
COMMENT ON COLUMN competitor_cleaned_rows.rejection_reason IS 'Reason when scoring_status is rejected or error.';
COMMENT ON COLUMN competitor_cleaned_rows.scored_at IS 'Timestamp when scoring was last applied.';

-- =============================================================================
-- Campaign Monitoring System (migration 019)
-- =============================================================================
CREATE TYPE campaign_lock_status AS ENUM ('active', 'locked');

CREATE TABLE campaign_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    status campaign_lock_status NOT NULL DEFAULT 'locked',
    acos_at_lock NUMERIC NULL,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ NOT NULL,
    unlocked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, campaign_name)
);

CREATE TABLE daily_budget_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    daily_budget NUMERIC NOT NULL DEFAULT 10,
    spend NUMERIC NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    orders INTEGER NOT NULL DEFAULT 0,
    sales NUMERIC NOT NULL DEFAULT 0,
    acos NUMERIC NULL,
    bid_multiplier NUMERIC NOT NULL DEFAULT 1.0,
    previous_bid NUMERIC NOT NULL DEFAULT 1.0,
    suggested_bid NUMERIC NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, product_id, campaign_name, snapshot_date)
);

CREATE TABLE day7_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    total_spend_7d NUMERIC NOT NULL,
    total_sales_7d NUMERIC NOT NULL,
    acos_7d NUMERIC NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('locked', 'continue_monitoring')),
    locked_until TIMESTAMPTZ NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, product_id, campaign_name)
);

CREATE TABLE product_competitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    competitor_name TEXT NOT NULL,
    competitor_asin TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, product_id, competitor_name)
);

ALTER TABLE competitor_cleaned_rows
    ADD COLUMN verification_status TEXT NULL CHECK (verification_status IN ('verified', 'unverified')),
    ADD COLUMN verification_result_json JSONB NULL,
    ADD COLUMN verified_at TIMESTAMPTZ NULL;

ALTER TABLE product_profiles
    ADD COLUMN keyword_batch_size INTEGER NOT NULL DEFAULT 7 CHECK (keyword_batch_size BETWEEN 5 AND 7);

CREATE INDEX campaign_locks_workspace_idx ON campaign_locks(workspace_id, campaign_name);
CREATE INDEX daily_budget_snapshots_date_idx ON daily_budget_snapshots(workspace_id, product_id, snapshot_date DESC);
CREATE INDEX day7_checkpoints_workspace_idx ON day7_checkpoints(workspace_id, product_id);
CREATE INDEX product_competitors_product_idx ON product_competitors(workspace_id, product_id);
CREATE INDEX competitor_cleaned_rows_verification_idx ON competitor_cleaned_rows(verification_status);

COMMENT ON TABLE campaign_locks IS 'Campaign freeze after Day 7 ACOS < 50% evaluation.';
COMMENT ON TABLE daily_budget_snapshots IS 'Per-campaign daily spend, impressions, clicks, orders, sales, and ACOS for 14-day monitoring cycle.';
COMMENT ON TABLE day7_checkpoints IS 'Day 7 ACOS evaluation results. ACOS < 50% triggers a 7-day campaign lock.';
COMMENT ON TABLE product_competitors IS 'Competitor names/ASINs for Amazon search verification.';

-- =============================================================================
-- Custom Agent Builder (migration 020)
-- =============================================================================
CREATE TABLE IF NOT EXISTS custom_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    role_instructions TEXT,
    model_provider TEXT NOT NULL DEFAULT 'deepseek',
    model_name TEXT NOT NULL DEFAULT 'deepseek-chat',
    temperature NUMERIC(3,2) DEFAULT 0.7 CHECK (temperature >= 0 AND temperature <= 2),
    max_tokens INTEGER DEFAULT 4096,
    memory_enabled BOOLEAN NOT NULL DEFAULT false,
    memory_ttl_days INTEGER DEFAULT 30,
    output_format TEXT DEFAULT 'text',
    output_schema JSONB,
    workflow_type TEXT DEFAULT 'sequential',
    workflow_graph JSONB,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id UUID NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    tool_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    permission_level TEXT NOT NULL DEFAULT 'read' CHECK (permission_level IN ('read', 'write', 'execute', 'admin')),
    requires_approval BOOLEAN NOT NULL DEFAULT false,
    rate_limit_per_day INTEGER,
    allowed_domains JSONB,
    allowed_actions JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id, tool_name)
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    source_type TEXT NOT NULL DEFAULT 'upload',
    file_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    embedding_provider TEXT DEFAULT 'openai',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'error')),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_base_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size_bytes BIGINT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'error')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- pgvector extension required for this table
-- CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS knowledge_base_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    file_id UUID REFERENCES knowledge_base_files(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    -- embedding vector(1536),  -- requires pgvector extension
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id UUID NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    retrieval_priority INTEGER DEFAULT 1,
    max_chunks_per_query INTEGER DEFAULT 5,
    similarity_threshold NUMERIC(3,2) DEFAULT 0.75,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id, knowledge_base_id)
);

CREATE TABLE IF NOT EXISTS sub_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    parent_agent_id UUID NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    instructions TEXT NOT NULL,
    model_provider TEXT,
    model_name TEXT,
    tools_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    execution_order INTEGER NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT true,
    requires_approval BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id UUID NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    thread_id UUID NOT NULL REFERENCES agent_threads(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES custom_agents(id) ON DELETE SET NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool', 'sub_agent')),
    content TEXT,
    tool_calls_json JSONB,
    tool_call_id TEXT,
    sub_agent_name TEXT,
    token_count INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- pgvector extension required for this table
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id UUID NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    thread_id UUID REFERENCES agent_threads(id) ON DELETE SET NULL,
    memory_type TEXT NOT NULL DEFAULT 'preference' CHECK (memory_type IN ('preference', 'fact', 'decision', 'context', 'user_info', 'project')),
    content TEXT NOT NULL,
    -- embedding vector(1536),  -- requires pgvector extension
    importance NUMERIC(3,2) DEFAULT 0.5,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS custom_agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id UUID NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    thread_id UUID REFERENCES agent_threads(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled', 'waiting_approval')),
    model_provider TEXT,
    model_name TEXT,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    cost_usd NUMERIC(12,6) DEFAULT 0,
    latency_ms INTEGER,
    sub_agent_runs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_call_count INTEGER DEFAULT 0,
    knowledge_chunks_retrieved INTEGER DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS custom_agent_run_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    run_id UUID NOT NULL REFERENCES custom_agent_runs(id) ON DELETE CASCADE,
    agent_name TEXT,
    step_type TEXT NOT NULL CHECK (step_type IN ('planner', 'research', 'tool_call', 'knowledge_retrieval', 'llm_call', 'sub_agent', 'reviewer', 'output_format', 'approval_check')),
    step_order INTEGER NOT NULL,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    error_message TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent_secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id UUID REFERENCES custom_agents(id) ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    secret_value_encrypted TEXT,
    secret_provider TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id, secret_name)
);

CREATE TABLE IF NOT EXISTS agent_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    config_json JSONB NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT true,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS custom_agents_workspace_idx ON custom_agents(workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS custom_agents_name_idx ON custom_agents(workspace_id, name);
CREATE INDEX IF NOT EXISTS agent_tools_agent_idx ON agent_tools(agent_id);
CREATE INDEX IF NOT EXISTS knowledge_bases_workspace_idx ON knowledge_bases(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS knowledge_base_files_kb_idx ON knowledge_base_files(knowledge_base_id, status);
CREATE INDEX IF NOT EXISTS knowledge_base_chunks_kb_idx ON knowledge_base_chunks(knowledge_base_id, chunk_index);
CREATE INDEX IF NOT EXISTS agent_knowledge_bases_agent_idx ON agent_knowledge_bases(agent_id, knowledge_base_id);
CREATE INDEX IF NOT EXISTS sub_agents_parent_idx ON sub_agents(parent_agent_id, execution_order);
CREATE INDEX IF NOT EXISTS agent_threads_agent_idx ON agent_threads(agent_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS agent_threads_workspace_idx ON agent_threads(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_messages_thread_idx ON agent_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS agent_memories_agent_idx ON agent_memories(agent_id, memory_type);
CREATE INDEX IF NOT EXISTS custom_agent_runs_agent_idx ON custom_agent_runs(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS custom_agent_runs_thread_idx ON custom_agent_runs(thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS custom_agent_run_steps_run_idx ON custom_agent_run_steps(run_id, step_order);
CREATE INDEX IF NOT EXISTS agent_secrets_agent_idx ON agent_secrets(agent_id, secret_name);

-- Seed agent templates
INSERT INTO agent_templates (name, description, category, config_json) VALUES
    ('Marketing Research Agent', 'Researches competitors, market trends, and writes content briefs.', 'marketing', '{"name":"Marketing Research Agent","role_instructions":"You are an expert marketing researcher.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.7,"memory_enabled":true,"tools":["web_search"],"sub_agents":[{"name":"Research Agent","role":"Analyze competitor websites","instructions":"Search for competitor information."},{"name":"Writer Agent","role":"Create polished marketing content","instructions":"Write clear, engaging marketing content."},{"name":"Reviewer Agent","role":"Check for accuracy and quality","instructions":"Verify facts and check grammar."}],"permissions":{"requires_approval_before_email":true,"can_read_web":true,"can_write_web":false}}'),
    ('Sales Outreach Agent', 'Qualifies leads, drafts personalized emails, and manages follow-up cadences.', 'sales', '{"name":"Sales Outreach Agent","role_instructions":"You are a professional sales development representative.","model_provider":"openai","model_name":"gpt-4o","temperature":0.5,"memory_enabled":true,"tools":["crm_lookup","email_draft"],"sub_agents":[{"name":"Lead Qualifier","role":"Evaluate lead fit and priority","instructions":"Score leads based on ICP criteria."},{"name":"Email Drafter","role":"Write personalized outreach emails","instructions":"Craft compelling, personalized emails."}],"permissions":{"requires_approval_before_email":true,"can_read_crm":true,"can_send_email":false}}'),
    ('Code Review Agent', 'Reviews pull requests, suggests improvements, checks security vulnerabilities.', 'development', '{"name":"Code Review Agent","role_instructions":"You are a senior software engineer performing code reviews.","model_provider":"openai","model_name":"gpt-4o","temperature":0.3,"memory_enabled":false,"tools":["github_repo_reader"],"sub_agents":[{"name":"Security Reviewer","role":"Check for security vulnerabilities","instructions":"Scan code for OWASP top 10 vulnerabilities."},{"name":"Performance Reviewer","role":"Identify performance issues","instructions":"Check for N+1 queries and memory leaks."},{"name":"Style Reviewer","role":"Check code style and best practices","instructions":"Verify code follows team conventions."}],"permissions":{"can_read_github":true,"can_write_github":false,"can_create_pr_comment":false}}'),
    ('Customer Support Agent', 'Answers customer questions from knowledge base, drafts responses.', 'support', '{"name":"Customer Support Agent","role_instructions":"You are a helpful customer support specialist.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.4,"memory_enabled":true,"tools":["knowledge_base_search","ticket_lookup"],"sub_agents":[],"permissions":{"can_read_knowledge_base":true,"can_read_tickets":true,"can_update_tickets":false,"requires_approval_before_customer_reply":true}}'),
    ('General Research Assistant', 'Versatile research agent with web search, file analysis, and summarization.', 'general', '{"name":"General Research Assistant","role_instructions":"You are a helpful research assistant.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.7,"memory_enabled":true,"tools":["web_search"],"sub_agents":[],"permissions":{"can_read_web":true}}')
ON CONFLICT DO NOTHING;

-- =============================================================================
-- Duplicate Detection & State Persistence (migration 021)
-- =============================================================================
ALTER TABLE uploads
    ADD COLUMN IF NOT EXISTS file_hash TEXT,
    ADD COLUMN IF NOT EXISTS file_hash_algorithm TEXT DEFAULT 'sha256';

CREATE INDEX IF NOT EXISTS uploads_file_hash_idx ON uploads(workspace_id, file_hash);

COMMENT ON COLUMN uploads.file_hash IS 'SHA-256 hash of the raw uploaded file content. Used for exact duplicate detection.';
COMMENT ON COLUMN uploads.file_hash_algorithm IS 'Hashing algorithm used to compute file_hash, currently always sha256.';

ALTER TABLE account_imports
    ADD COLUMN IF NOT EXISTS data_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS data_fingerprint_version TEXT DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS account_imports_fingerprint_idx ON account_imports(workspace_id, data_fingerprint);

COMMENT ON COLUMN account_imports.data_fingerprint IS 'Normalized business data fingerprint (hash of workspace, report_type, date_range, row_count, key metrics).';
COMMENT ON COLUMN account_imports.data_fingerprint_version IS 'Version of the fingerprint algorithm.';

CREATE INDEX IF NOT EXISTS account_import_entities_key_idx ON account_import_entities(workspace_id, entity_type, entity_key);

ALTER TABLE recommendations
    ADD COLUMN IF NOT EXISTS recommendation_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS fingerprint_version TEXT DEFAULT 'v1',
    ADD COLUMN IF NOT EXISTS superseded_by_id UUID REFERENCES recommendations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS recommendations_fingerprint_idx ON recommendations(workspace_id, recommendation_fingerprint);

COMMENT ON COLUMN recommendations.recommendation_fingerprint IS 'Deterministic fingerprint of the recommendation.';
COMMENT ON COLUMN recommendations.superseded_by_id IS 'When a newer run produces a recommendation that supersedes this one, points to the newer recommendation.';

ALTER TYPE upload_status ADD VALUE IF NOT EXISTS 'duplicate_detected';
ALTER TYPE upload_status ADD VALUE IF NOT EXISTS 'archived';

ALTER TABLE account_imports
    DROP CONSTRAINT IF EXISTS account_imports_status_check;

ALTER TABLE account_imports
    ADD CONSTRAINT account_imports_status_check
    CHECK (
        status IN (
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

ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'draft';
ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'validated';
ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'rejected_by_validator';
ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'repeated';
ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'conflicting';
ALTER TYPE recommendation_status ADD VALUE IF NOT EXISTS 'exported';

ALTER TABLE agent_workflows
    ADD COLUMN IF NOT EXISTS run_number INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS strategy_profile TEXT;

CREATE INDEX IF NOT EXISTS agent_workflows_import_run_idx ON agent_workflows(account_import_id, run_number);

COMMENT ON COLUMN agent_workflows.run_number IS 'Sequential run number within a given account import (1, 2, 3...).';
COMMENT ON COLUMN agent_workflows.strategy_profile IS 'Strategy label for this run (e.g., conservative, balanced, growth).';

ALTER TABLE uploads
    ADD COLUMN IF NOT EXISTS duplicate_detected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS previous_upload_id UUID REFERENCES uploads(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS duplicate_type TEXT CHECK (duplicate_type IN ('exact_file_duplicate', 'same_data_duplicate', NULL));

COMMENT ON COLUMN uploads.duplicate_detected_at IS 'When duplicate detection flagged this upload.';
COMMENT ON COLUMN uploads.previous_upload_id IS 'Reference to the previous upload that this one duplicates.';
COMMENT ON COLUMN uploads.duplicate_type IS 'Type of duplicate detected: exact_file_duplicate or same_data_duplicate.';

CREATE TABLE IF NOT EXISTS dashboard_summary_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '5 minutes'),
    UNIQUE (workspace_id)
);

CREATE INDEX IF NOT EXISTS dashboard_summary_cache_workspace_idx ON dashboard_summary_cache(workspace_id);

COMMENT ON TABLE dashboard_summary_cache IS 'Cached dashboard summary for fast refresh recovery.';

-- =============================================================================
-- Phase 3 Monitoring Backbone (migration 022)
-- =============================================================================
CREATE TABLE IF NOT EXISTS daily_monitoring_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL,
    product_id      UUID NOT NULL,
    campaign_name   TEXT NOT NULL,
    ad_group_name   TEXT NOT NULL DEFAULT '',
    targeting       TEXT NOT NULL DEFAULT '',
    customer_search_term TEXT NOT NULL DEFAULT '',
    match_type      TEXT,
    snapshot_date   DATE NOT NULL,
    impressions     INTEGER NOT NULL DEFAULT 0,
    clicks          INTEGER NOT NULL DEFAULT 0,
    spend           NUMERIC(12,4) NOT NULL DEFAULT 0,
    sales           NUMERIC(12,4) NOT NULL DEFAULT 0,
    orders          INTEGER NOT NULL DEFAULT 0,
    units           INTEGER,
    cpc             NUMERIC(12,4),
    ctr             NUMERIC(9,4),
    cvr             NUMERIC(9,4),
    acos            NUMERIC(9,4),
    roas            NUMERIC(12,4),
    raw_metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_import_id UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, product_id, campaign_name, ad_group_name, targeting, customer_search_term, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_snaps_ws_product_date
    ON daily_monitoring_snapshots (workspace_id, product_id, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_snaps_ws_campaign
    ON daily_monitoring_snapshots (workspace_id, campaign_name, snapshot_date DESC);

CREATE TABLE IF NOT EXISTS day7_acos_checkpoints (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL,
    product_id              UUID NOT NULL,
    recommendation_id       UUID NOT NULL,
    approved_at             TIMESTAMPTZ NOT NULL,
    checkpoint_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    pre_acos                NUMERIC(9,4) NOT NULL,
    pre_spend               NUMERIC(12,4) NOT NULL,
    pre_sales               NUMERIC(12,4) NOT NULL,
    pre_clicks              INTEGER NOT NULL,
    pre_orders              INTEGER NOT NULL,
    post_acos               NUMERIC(9,4),
    post_spend              NUMERIC(12,4),
    post_sales              NUMERIC(12,4),
    post_clicks             INTEGER,
    post_orders             INTEGER,
    acos_delta_pct          NUMERIC(9,4),
    sales_delta_pct         NUMERIC(9,4),
    outcome                 TEXT,
    snapshot_days_used      INTEGER NOT NULL DEFAULT 7,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (recommendation_id)
);

CREATE INDEX IF NOT EXISTS idx_day7_checkpoints_ws_product
    ON day7_acos_checkpoints (workspace_id, product_id);
CREATE INDEX IF NOT EXISTS idx_day7_checkpoints_outcome
    ON day7_acos_checkpoints (outcome)
    WHERE outcome IS NOT NULL;

CREATE TABLE IF NOT EXISTS campaign_lock_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL,
    product_id      UUID NOT NULL,
    campaign_name   TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_key      TEXT NOT NULL,
    lock_type       TEXT NOT NULL,
    locked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until    TIMESTAMPTZ,
    locked_by       TEXT,
    reason          TEXT,
    recommendation_id UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_lock_ws
    ON campaign_lock_state (workspace_id, product_id, campaign_name);
CREATE INDEX IF NOT EXISTS idx_campaign_lock_time
    ON campaign_lock_state (locked_until)
    WHERE locked_until IS NOT NULL;

CREATE TABLE IF NOT EXISTS rule_calibration (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID NOT NULL,
    product_id          UUID,
    rule_name           TEXT NOT NULL,
    parameter           TEXT NOT NULL,
    original_value      NUMERIC(12,4) NOT NULL,
    current_value       NUMERIC(12,4) NOT NULL,
    adjustment_pct      NUMERIC(9,4) NOT NULL DEFAULT 0,
    bounded_min         NUMERIC(12,4) NOT NULL,
    bounded_max         NUMERIC(12,4) NOT NULL,
    feedback_cycle      INTEGER NOT NULL DEFAULT 1,
    outcome_evidence    JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_adjusted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rule_calibration_ws_rule
    ON rule_calibration (workspace_id, rule_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_calibration_unique
    ON rule_calibration (workspace_id, COALESCE(product_id, '00000000-0000-0000-0000-000000000000'::uuid), rule_name, parameter);

-- Token usage view (migration 022 + 023, stripped of RLS)
-- Ensure workspace_id exists on ai_runs
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_runs' AND column_name = 'workspace_id'
    ) THEN
        ALTER TABLE ai_runs ADD COLUMN workspace_id UUID;
        CREATE INDEX IF NOT EXISTS idx_ai_runs_workspace ON ai_runs (workspace_id);
    END IF;
END $$;

CREATE OR REPLACE VIEW token_usage_by_workspace AS
SELECT
    workspace_id,
    provider,
    model,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded_calls,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_calls,
    SUM(latency_ms) AS total_latency_ms,
    AVG(latency_ms)::INTEGER AS avg_latency_ms,
    SUM(COALESCE((output_json->'usage'->>'total_tokens')::INTEGER, 0)) AS estimated_total_tokens,
    SUM(COALESCE((output_json->'usage'->>'prompt_tokens')::INTEGER, 0)) AS estimated_prompt_tokens,
    SUM(COALESCE((output_json->'usage'->>'completion_tokens')::INTEGER, 0)) AS estimated_completion_tokens,
    MIN(created_at) AS first_call_at,
    MAX(created_at) AS last_call_at
FROM ai_runs
GROUP BY workspace_id, provider, model
ORDER BY workspace_id, total_calls DESC;

COMMENT ON VIEW token_usage_by_workspace IS
    'Per-workspace AI token and cost attribution view. Sources from ai_runs table.';

COMMIT;
