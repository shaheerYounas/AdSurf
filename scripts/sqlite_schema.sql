-- =============================================================================
-- AdSurf SQLite Schema (Offline, Zero-Server)
-- Converted from 24 Supabase PostgreSQL migrations.
-- All PostgreSQL-specific features removed: no enums, jsonb, gen_random_uuid(),
-- timestamptz, pgcrypto, RLS, auth functions, triggers, or complex casts.
-- =============================================================================

-- =============================================================================
-- Core tables
-- =============================================================================
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'seller',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE workspace_members (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'analyst', 'approver', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'invited', 'disabled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, user_id)
);

INSERT OR IGNORE INTO workspaces (id, name, type, status, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Local Demo Workspace',
    'seller',
    'active',
    datetime('now'),
    datetime('now')
);

INSERT OR IGNORE INTO workspace_members (id, workspace_id, user_id, role, status, created_at, updated_at)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'owner',
    'active',
    datetime('now'),
    datetime('now')
);

CREATE TABLE product_profiles (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_name TEXT NOT NULL,
    asin TEXT NULL CHECK (asin IS NULL OR asin GLOB '[A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9]'),
    sku TEXT NULL,
    marketplace TEXT NOT NULL DEFAULT 'US',
    currency TEXT NOT NULL DEFAULT 'USD' CHECK (LENGTH(currency) = 3),
    target_acos REAL NOT NULL DEFAULT 0.5000 CHECK (target_acos > 0 AND target_acos <= 1),
    default_budget REAL NOT NULL DEFAULT 10.0000 CHECK (default_budget > 0),
    default_bid REAL NOT NULL DEFAULT 1.0000 CHECK (default_bid > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_by TEXT NULL,
    updated_by TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    keyword_batch_size INTEGER NOT NULL DEFAULT 7 CHECK (keyword_batch_size BETWEEN 5 AND 7)
);

CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    actor_user_id TEXT NULL,
    event_type TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE rule_versions (
    id TEXT PRIMARY KEY,
    rule_set TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    active_from TEXT NOT NULL,
    active_to TEXT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (rule_set, version)
);

CREATE TABLE job_queue (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_at TEXT NULL,
    locked_by TEXT NULL,
    heartbeat_at TEXT NULL,
    last_error TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, job_type, idempotency_key)
);

CREATE TABLE outbox_events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'failed')),
    published_at TEXT NULL,
    created_at TEXT NOT NULL
);

-- Core indexes
CREATE INDEX idx_workspace_members_workspace_id ON workspace_members(workspace_id);
CREATE INDEX idx_workspace_members_user_id ON workspace_members(user_id);
CREATE INDEX idx_product_profiles_workspace_id ON product_profiles(workspace_id);
CREATE INDEX idx_product_profiles_status ON product_profiles(status);
CREATE UNIQUE INDEX product_profiles_workspace_id_id_unique ON product_profiles(workspace_id, id);
CREATE INDEX idx_audit_logs_workspace_id_created_at ON audit_logs(workspace_id, created_at DESC);
CREATE INDEX idx_rule_versions_rule_set ON rule_versions(rule_set);
CREATE INDEX idx_job_queue_status_locked_at ON job_queue(status, locked_at);
CREATE INDEX idx_job_queue_workspace_id ON job_queue(workspace_id);
CREATE INDEX idx_outbox_events_status_created_at ON outbox_events(status, created_at);

-- =============================================================================
-- Uploads
-- =============================================================================
CREATE TABLE uploads (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT NULL,
    uploaded_by TEXT,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    file_size_bytes INTEGER CHECK (file_size_bytes IS NULL OR file_size_bytes > 0),
    status TEXT NOT NULL DEFAULT 'initialized' CHECK (status IN ('initialized', 'uploaded', 'queued_for_processing', 'processing', 'processed', 'failed', 'cancelled')),
    source_type TEXT NOT NULL CHECK (source_type IN (
        'competitor_keyword_research', 'amazon_ads_sp_search_term_report',
        'single_product_report', 'account_bulk_report', 'sponsored_products_search_term_report',
        'sponsored_products_targeting_report', 'sponsored_products_campaign_report',
        'bulk_sheet', 'unknown_report'
    )),
    idempotency_key TEXT,
    file_hash TEXT,
    file_hash_algorithm TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT,
    UNIQUE (workspace_id, idempotency_key),
    UNIQUE (workspace_id, product_id, id),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT
);

CREATE INDEX uploads_workspace_id_idx ON uploads(workspace_id);
CREATE INDEX uploads_product_id_idx ON uploads(product_id);
CREATE INDEX uploads_status_idx ON uploads(status);
CREATE INDEX uploads_created_at_idx ON uploads(created_at);
CREATE INDEX uploads_idempotency_key_idx ON uploads(idempotency_key);
CREATE INDEX uploads_workspace_created_desc_idx ON uploads(workspace_id, created_at DESC);
CREATE INDEX uploads_workspace_status_created_desc_idx ON uploads(workspace_id, status, created_at DESC);

-- =============================================================================
-- Upload Parse
-- =============================================================================
CREATE TABLE upload_parse_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT NULL,
    upload_id TEXT NOT NULL,
    job_id TEXT NOT NULL UNIQUE REFERENCES job_queue(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    parser_version TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    detected_file_type TEXT NOT NULL,
    detected_sheet_names TEXT NOT NULL DEFAULT '[]',
    selected_sheet_name TEXT,
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    total_columns INTEGER NOT NULL DEFAULT 0 CHECK (total_columns >= 0),
    parsed_rows_count INTEGER NOT NULL DEFAULT 0 CHECK (parsed_rows_count >= 0),
    error_rows_count INTEGER NOT NULL DEFAULT 0 CHECK (error_rows_count >= 0),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT,
    UNIQUE (id, workspace_id, product_id, upload_id),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, product_id, upload_id) REFERENCES uploads(workspace_id, product_id, id) ON DELETE RESTRICT
);

CREATE TABLE upload_parsed_rows (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    product_id TEXT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL REFERENCES upload_parse_runs(id) ON DELETE RESTRICT,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    row_data_json TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (parse_run_id, row_number),
    FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id) REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, product_id, upload_id) REFERENCES uploads(workspace_id, product_id, id) ON DELETE RESTRICT
);

CREATE TABLE upload_parse_errors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    product_id TEXT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL REFERENCES upload_parse_runs(id) ON DELETE RESTRICT,
    row_number INTEGER CHECK (row_number IS NULL OR row_number > 0),
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    raw_value_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id) REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, product_id, upload_id) REFERENCES uploads(workspace_id, product_id, id) ON DELETE RESTRICT
);

CREATE INDEX upload_parse_runs_workspace_upload_idx ON upload_parse_runs(workspace_id, upload_id, created_at DESC);
CREATE INDEX upload_parsed_rows_parse_run_idx ON upload_parsed_rows(parse_run_id, row_number);
CREATE INDEX upload_parse_errors_parse_run_idx ON upload_parse_errors(parse_run_id, row_number);

-- =============================================================================
-- Column Mapping
-- =============================================================================
CREATE TABLE upload_column_profiles (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('generated', 'failed')),
    total_columns INTEGER NOT NULL DEFAULT 0 CHECK (total_columns >= 0),
    total_rows_sampled INTEGER NOT NULL DEFAULT 0 CHECK (total_rows_sampled >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (parse_run_id),
    UNIQUE (id, workspace_id, product_id, upload_id, parse_run_id),
    FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id) REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id) ON DELETE RESTRICT
);

CREATE TABLE upload_column_profile_columns (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL,
    column_profile_id TEXT NOT NULL,
    original_column_name TEXT NOT NULL,
    normalized_column_name TEXT NOT NULL,
    column_index INTEGER NOT NULL CHECK (column_index >= 0),
    non_null_count INTEGER NOT NULL DEFAULT 0 CHECK (non_null_count >= 0),
    sample_values_json TEXT NOT NULL DEFAULT '[]',
    inferred_data_type TEXT NOT NULL CHECK (inferred_data_type IN ('text', 'integer', 'decimal', 'date', 'boolean', 'unknown')),
    created_at TEXT NOT NULL,
    UNIQUE (column_profile_id, column_index),
    UNIQUE (column_profile_id, original_column_name),
    FOREIGN KEY (column_profile_id, workspace_id, product_id, upload_id, parse_run_id) REFERENCES upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id) ON DELETE RESTRICT
);

CREATE TABLE upload_column_mappings (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL,
    column_profile_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'valid', 'invalid', 'approved', 'superseded')),
    mapping_version INTEGER NOT NULL CHECK (mapping_version > 0),
    mapping_type TEXT NOT NULL DEFAULT 'manual' CHECK (mapping_type IN ('manual')),
    mapping_json TEXT NOT NULL,
    validation_errors_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    UNIQUE (column_profile_id, mapping_version),
    UNIQUE (id, workspace_id, product_id, upload_id, parse_run_id),
    FOREIGN KEY (column_profile_id, workspace_id, product_id, upload_id, parse_run_id) REFERENCES upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id) ON DELETE RESTRICT
);

CREATE INDEX upload_column_profiles_workspace_upload_idx ON upload_column_profiles(workspace_id, upload_id, created_at DESC);
CREATE INDEX upload_column_profile_columns_profile_idx ON upload_column_profile_columns(column_profile_id, column_index);
CREATE INDEX upload_column_mappings_profile_idx ON upload_column_mappings(column_profile_id, mapping_version DESC);
CREATE INDEX upload_column_mappings_workspace_upload_idx ON upload_column_mappings(workspace_id, upload_id, created_at DESC);

-- =============================================================================
-- Keyword Scoring
-- =============================================================================
CREATE TABLE keyword_scoring_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    parse_run_id TEXT NOT NULL,
    column_mapping_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    scoring_version INTEGER NOT NULL,
    rule_version_id TEXT NULL REFERENCES rule_versions(id),
    idempotency_key TEXT NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    scored_rows INTEGER NOT NULL DEFAULT 0 CHECK (scored_rows >= 0),
    approved_count INTEGER NOT NULL DEFAULT 0 CHECK (approved_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    started_at TEXT NOT NULL,
    completed_at TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT NULL,
    UNIQUE (column_mapping_id, scoring_version),
    UNIQUE (workspace_id, idempotency_key),
    UNIQUE (id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id),
    UNIQUE (id, workspace_id, product_id, column_mapping_id),
    FOREIGN KEY (column_mapping_id, workspace_id, product_id, upload_id, parse_run_id) REFERENCES upload_column_mappings(id, workspace_id, product_id, upload_id, parse_run_id)
);

CREATE TABLE keyword_candidates (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    parse_run_id TEXT NOT NULL,
    column_mapping_id TEXT NOT NULL,
    scoring_run_id TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    search_term TEXT NULL,
    search_volume REAL NULL,
    competitor_rank_values_json TEXT NOT NULL DEFAULT '[]',
    relevance_score INTEGER NULL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 10),
    scoring_status TEXT NOT NULL CHECK (scoring_status IN ('approved', 'rejected', 'error')),
    rejection_reason TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (id, workspace_id, product_id, scoring_run_id),
    FOREIGN KEY (scoring_run_id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id) REFERENCES keyword_scoring_runs(id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id) ON DELETE CASCADE,
    CHECK (scoring_status = 'error' OR (search_term IS NOT NULL AND TRIM(search_term) != ''))
);

CREATE INDEX keyword_scoring_runs_workspace_upload_idx ON keyword_scoring_runs(workspace_id, upload_id, created_at DESC);
CREATE INDEX keyword_candidates_workspace_product_idx ON keyword_candidates(workspace_id, product_id);
CREATE INDEX keyword_candidates_upload_idx ON keyword_candidates(upload_id);
CREATE INDEX keyword_candidates_scoring_run_idx ON keyword_candidates(scoring_run_id);
CREATE INDEX keyword_candidates_scoring_status_idx ON keyword_candidates(scoring_status);
CREATE INDEX keyword_candidates_relevance_score_idx ON keyword_candidates(relevance_score);
CREATE INDEX keyword_candidates_search_term_idx ON keyword_candidates(search_term);

-- =============================================================================
-- Keyword Review
-- =============================================================================
CREATE TABLE keyword_candidate_overrides (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    product_id TEXT NOT NULL,
    scoring_run_id TEXT NOT NULL,
    keyword_candidate_id TEXT NOT NULL,
    override_action TEXT NOT NULL CHECK (override_action IN ('approve', 'reject')),
    original_scoring_status TEXT NOT NULL CHECK (original_scoring_status IN ('approved', 'rejected')),
    new_status TEXT NOT NULL CHECK (new_status IN ('approved', 'rejected')),
    reason TEXT NOT NULL CHECK (LENGTH(TRIM(reason)) > 0),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (keyword_candidate_id),
    FOREIGN KEY (keyword_candidate_id, workspace_id, product_id, scoring_run_id) REFERENCES keyword_candidates(id, workspace_id, product_id, scoring_run_id) ON DELETE RESTRICT,
    CHECK (
        (override_action = 'approve' AND new_status = 'approved')
        OR (override_action = 'reject' AND new_status = 'rejected')
    )
);

CREATE TABLE approved_keyword_sets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    product_id TEXT NOT NULL,
    scoring_run_id TEXT NOT NULL,
    column_mapping_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK (LENGTH(TRIM(name)) > 0),
    status TEXT NOT NULL DEFAULT 'locked' CHECK (status IN ('created', 'locked', 'superseded')),
    keyword_count INTEGER NOT NULL DEFAULT 0 CHECK (keyword_count >= 0),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    UNIQUE (id, workspace_id, product_id),
    FOREIGN KEY (scoring_run_id, workspace_id, product_id, column_mapping_id) REFERENCES keyword_scoring_runs(id, workspace_id, product_id, column_mapping_id) ON DELETE RESTRICT
);

CREATE TABLE approved_keyword_set_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    product_id TEXT NOT NULL,
    approved_keyword_set_id TEXT NOT NULL,
    scoring_run_id TEXT NOT NULL,
    keyword_candidate_id TEXT NOT NULL,
    search_term TEXT NOT NULL CHECK (LENGTH(TRIM(search_term)) > 0),
    search_volume REAL,
    relevance_score INTEGER NOT NULL CHECK (relevance_score BETWEEN 0 AND 10),
    source_status TEXT NOT NULL CHECK (source_status IN ('approved', 'rejected', 'error')),
    final_status TEXT NOT NULL DEFAULT 'approved' CHECK (final_status = 'approved'),
    override_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (approved_keyword_set_id, keyword_candidate_id),
    FOREIGN KEY (approved_keyword_set_id, workspace_id, product_id) REFERENCES approved_keyword_sets(id, workspace_id, product_id) ON DELETE RESTRICT,
    FOREIGN KEY (keyword_candidate_id, workspace_id, product_id, scoring_run_id) REFERENCES keyword_candidates(id, workspace_id, product_id, scoring_run_id) ON DELETE RESTRICT,
    FOREIGN KEY (override_id) REFERENCES keyword_candidate_overrides(id) ON DELETE RESTRICT
);

CREATE INDEX keyword_candidate_overrides_workspace_product_idx ON keyword_candidate_overrides(workspace_id, product_id);
CREATE INDEX keyword_candidate_overrides_scoring_run_idx ON keyword_candidate_overrides(scoring_run_id);
CREATE INDEX approved_keyword_sets_workspace_product_idx ON approved_keyword_sets(workspace_id, product_id);
CREATE INDEX approved_keyword_sets_scoring_run_idx ON approved_keyword_sets(scoring_run_id);
CREATE INDEX approved_keyword_set_items_set_idx ON approved_keyword_set_items(approved_keyword_set_id);
CREATE INDEX approved_keyword_set_items_scoring_run_idx ON approved_keyword_set_items(scoring_run_id);
CREATE INDEX approved_keyword_set_items_search_term_idx ON approved_keyword_set_items(search_term);

-- =============================================================================
-- Campaign Export
-- =============================================================================
CREATE TABLE campaign_plans (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    product_id TEXT NOT NULL,
    approved_keyword_set_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('generated', 'approved', 'rejected', 'superseded')),
    rule_version_id TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    approved_by TEXT,
    approval_note TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, product_id, version),
    FOREIGN KEY (product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT,
    FOREIGN KEY (approved_keyword_set_id, workspace_id, product_id) REFERENCES approved_keyword_sets(id, workspace_id, product_id) ON DELETE RESTRICT
);

CREATE TABLE bulk_exports (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    product_id TEXT NOT NULL,
    campaign_plan_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'failed')),
    storage_path TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL CHECK (LENGTH(TRIM(original_filename)) > 0),
    rows_json TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approval_note TEXT NOT NULL CHECK (LENGTH(TRIM(approval_note)) > 0),
    approved_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (campaign_plan_id) REFERENCES campaign_plans(id) ON DELETE RESTRICT,
    FOREIGN KEY (product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT
);

CREATE INDEX campaign_plans_workspace_product_idx ON campaign_plans(workspace_id, product_id);
CREATE INDEX campaign_plans_keyword_set_idx ON campaign_plans(approved_keyword_set_id);
CREATE INDEX bulk_exports_workspace_product_idx ON bulk_exports(workspace_id, product_id);
CREATE INDEX bulk_exports_plan_idx ON bulk_exports(campaign_plan_id);

-- =============================================================================
-- Monitoring & Recommendations
-- =============================================================================
CREATE TABLE monitoring_imports (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type = 'sponsored_products_search_term'),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'succeeded', 'failed')),
    date_range_start TEXT,
    date_range_end TEXT,
    total_rows INTEGER NOT NULL DEFAULT 0,
    processed_rows INTEGER NOT NULL DEFAULT 0,
    error_rows INTEGER NOT NULL DEFAULT 0,
    data_quality_warnings_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, product_id, upload_id, report_type),
    FOREIGN KEY (product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, product_id, upload_id) REFERENCES uploads(workspace_id, product_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (parse_run_id, workspace_id, product_id, upload_id) REFERENCES upload_parse_runs(id, workspace_id, product_id, upload_id) ON DELETE RESTRICT
);

CREATE TABLE monitoring_snapshots (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL,
    monitoring_import_id TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    targeting TEXT NOT NULL,
    match_type TEXT,
    customer_search_term TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    spend REAL NOT NULL DEFAULT 0,
    sales REAL NOT NULL DEFAULT 0,
    orders INTEGER NOT NULL DEFAULT 0,
    units INTEGER,
    cpc REAL,
    ctr REAL,
    cvr REAL,
    acos REAL,
    roas REAL,
    raw_metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (monitoring_import_id) REFERENCES monitoring_imports(id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, product_id, upload_id) REFERENCES uploads(workspace_id, product_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (source_row_id) REFERENCES upload_parsed_rows(id) ON DELETE RESTRICT
);

CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT,
    monitoring_import_id TEXT,
    snapshot_id TEXT,
    account_import_id TEXT REFERENCES account_imports(id) ON DELETE RESTRICT,
    recommendation_type TEXT NOT NULL CHECK (recommendation_type IN (
        'increase_bid', 'decrease_bid', 'pause_review', 'negative_keyword_review', 'watch_lock',
        'keep_running', 'add_negative_exact', 'add_negative_phrase', 'move_to_exact',
        'data_quality_review', 'budget_review'
    )),
    status TEXT NOT NULL DEFAULT 'pending_approval' CHECK (status IN ('pending', 'pending_approval', 'approved', 'rejected', 'superseded')),
    priority TEXT NOT NULL CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    rule_version_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    targeting TEXT NOT NULL,
    customer_search_term TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'search_term' CHECK (entity_type IN ('account', 'product', 'campaign', 'ad_group', 'target', 'search_term')),
    entity_key TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    input_metrics_json TEXT NOT NULL,
    current_metric_snapshot_json TEXT NOT NULL DEFAULT '{}',
    proposed_action_json TEXT NOT NULL,
    explanation_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    decision_source TEXT,
    agent_run_id TEXT,
    ai_run_id TEXT,
    approval_boundary TEXT NOT NULL DEFAULT '{"requires_human_approval": true, "executes_live_amazon_change": false}',
    decided_by TEXT,
    decision_note TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT,
    FOREIGN KEY (monitoring_import_id) REFERENCES monitoring_imports(id) ON DELETE RESTRICT,
    FOREIGN KEY (snapshot_id) REFERENCES monitoring_snapshots(id) ON DELETE RESTRICT
);

CREATE TABLE recommendation_decisions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    recommendation_id TEXT NOT NULL REFERENCES recommendations(id) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor_user_id TEXT NOT NULL,
    note TEXT NOT NULL CHECK (LENGTH(TRIM(note)) > 0),
    created_at TEXT NOT NULL
);

CREATE TABLE ai_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_json TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    product_id TEXT,
    agent_id TEXT,
    monitoring_import_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    stopped_at TEXT,
    paused_at TEXT,
    controlled_by TEXT,
    control_reason TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    dependency_agent_run_ids TEXT NOT NULL DEFAULT '[]',
    recommendation_ids TEXT NOT NULL DEFAULT '[]',
    mode TEXT,
    strictness_level TEXT,
    confidence_threshold TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX monitoring_imports_workspace_product_idx ON monitoring_imports(workspace_id, product_id, created_at DESC);
CREATE INDEX monitoring_imports_upload_report_idx ON monitoring_imports(workspace_id, product_id, upload_id, report_type);
CREATE INDEX monitoring_snapshots_workspace_product_idx ON monitoring_snapshots(workspace_id, product_id);
CREATE INDEX recommendations_workspace_status_idx ON recommendations(workspace_id, status, priority);
CREATE INDEX recommendations_workspace_type_idx ON recommendations(workspace_id, recommendation_type);
CREATE INDEX recommendations_workspace_product_status_priority_created_idx ON recommendations(workspace_id, product_id, status, priority, created_at DESC);
CREATE INDEX recommendations_workspace_priority_created_idx ON recommendations(workspace_id, priority, created_at DESC);
CREATE INDEX recommendations_account_import_idx ON recommendations(workspace_id, account_import_id, entity_type);
CREATE INDEX recommendation_decisions_workspace_idx ON recommendation_decisions(workspace_id, recommendation_id);
CREATE INDEX ai_runs_workspace_agent_idx ON ai_runs(workspace_id, agent_name, created_at DESC);
CREATE INDEX ai_runs_workspace_product_agent_created_idx ON ai_runs(workspace_id, product_id, agent_name, created_at DESC);
CREATE INDEX ai_runs_monitoring_import_idx ON ai_runs(workspace_id, monitoring_import_id, created_at DESC);

-- =============================================================================
-- Agent Control Center
-- =============================================================================
CREATE TABLE agent_definitions (
    agent_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    task_type TEXT NOT NULL,
    enabled_by_default INTEGER NOT NULL DEFAULT 1,
    allowed_actions TEXT NOT NULL DEFAULT '[]',
    input_dependencies TEXT NOT NULL DEFAULT '[]',
    output_type TEXT NOT NULL,
    can_be_disabled INTEGER NOT NULL DEFAULT 1,
    can_be_rerun INTEGER NOT NULL DEFAULT 1,
    can_be_stopped INTEGER NOT NULL DEFAULT 1,
    requires_human_approval INTEGER NOT NULL DEFAULT 1,
    can_mutate_live_amazon_ads INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO agent_definitions (
    agent_id, display_name, description, task_type, enabled_by_default, allowed_actions,
    input_dependencies, output_type, can_be_disabled, can_be_rerun, can_be_stopped,
    requires_human_approval, can_mutate_live_amazon_ads, created_at, updated_at
)
VALUES
    ('performance_import_agent', 'Performance Import Agent', 'Validates report quality, missing columns, row count, and data-quality warnings.', 'validation', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs"]', '[]', 'report_quality_summary', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('metrics_analysis_agent', 'Metrics Analysis Agent', 'Analyzes uploaded Amazon Ads performance metrics and finds winners, wasters, and risks.', 'analysis', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs"]', '["performance_import_agent"]', 'performance_summary', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('ai_recommendation_brain_agent', 'AI Recommendation Brain', 'Uses DeepSeek or configured fallback mode to generate recommendation decisions from normalized report evidence.', 'decision', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]', '["metrics_analysis_agent"]', 'recommendation_json', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('bid_optimization_agent', 'Bid Optimization Agent', 'Reviews bid-related recommendations and explains increase, decrease, watch-lock, and bid risk logic.', 'explanation', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]', '["ai_recommendation_brain_agent"]', 'bid_recommendation_explanations', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('negative_keyword_agent', 'Negative Keyword Agent', 'Reviews wasted search terms and explains negative exact or phrase evidence.', 'explanation', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]', '["ai_recommendation_brain_agent"]', 'negative_keyword_explanations', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('pause_review_agent', 'Pause Review Agent', 'Reviews campaigns, ad groups, targets, or search terms that may need pause review.', 'explanation', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]', '["ai_recommendation_brain_agent"]', 'pause_review_explanations', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('stakeholder_reporting_agent', 'Stakeholder Reporting Agent', 'Creates dashboard summaries, executive summary, next-best actions, and approver notes.', 'reporting', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs"]', '["bid_optimization_agent","negative_keyword_agent","pause_review_agent"]', 'dashboard_summary', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('report_upload_node', 'Report Upload', 'Receives Amazon Ads reports or bulk sheets and starts the account import workflow.', 'start', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs"]', '[]', 'uploaded_report', 0, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('report_detection_agent', 'Report Detection Agent', 'Classifies the uploaded report type, required columns, confidence, and available entity levels.', 'validation', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs"]', '["report_upload_node"]', 'report_detection_summary', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('product_resolution_agent', 'Product Resolution Agent', 'Detects ASINs, SKUs, product names, and mapping suggestions before account-level analysis.', 'mapping', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs"]', '["report_detection_agent"]', 'product_mapping_suggestions', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('budget_allocation_agent', 'Budget Allocation Agent', 'Reviews campaign and product budget pressure and suggests approval-gated budget review actions.', 'explanation', 1, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]', '["ai_recommendation_brain_agent"]', 'budget_recommendation_explanations', 1, 1, 1, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('human_approval_agent', 'Human Approval Agent', 'Routes recommendations to the approval queue and prevents automatic approval or live ad mutation.', 'approval', 1, '["view_input","view_output","view_logs","view_recommendations"]', '["stakeholder_reporting_agent"]', 'approval_queue', 0, 0, 0, 1, 0, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00');

CREATE TABLE agent_configs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT,
    agent_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'hybrid' CHECK (mode IN ('deterministic', 'ai', 'hybrid')),
    strictness_level TEXT NOT NULL DEFAULT 'balanced' CHECK (strictness_level IN ('conservative', 'balanced', 'aggressive')),
    confidence_threshold TEXT NOT NULL DEFAULT 'medium' CHECK (confidence_threshold IN ('low', 'medium', 'high')),
    max_recommendations INTEGER NOT NULL DEFAULT 100 CHECK (max_recommendations > 0 AND max_recommendations <= 1000),
    allow_bid_recommendations INTEGER NOT NULL DEFAULT 1,
    allow_negative_keyword_recommendations INTEGER NOT NULL DEFAULT 1,
    allow_pause_recommendations INTEGER NOT NULL DEFAULT 1,
    allow_budget_recommendations INTEGER NOT NULL DEFAULT 1,
    provider TEXT NOT NULL DEFAULT 'deepseek',
    model TEXT,
    max_rows_per_ai_call INTEGER NOT NULL DEFAULT 500 CHECK (max_rows_per_ai_call > 0),
    max_products_per_run INTEGER NOT NULL DEFAULT 50 CHECK (max_products_per_run > 0),
    max_groups_per_ai_call INTEGER NOT NULL DEFAULT 100 CHECK (max_groups_per_ai_call > 0),
    analysis_depth TEXT NOT NULL DEFAULT 'standard' CHECK (analysis_depth IN ('quick', 'standard', 'deep')),
    include_account_level_analysis INTEGER NOT NULL DEFAULT 1,
    include_product_level_analysis INTEGER NOT NULL DEFAULT 1,
    include_campaign_level_analysis INTEGER NOT NULL DEFAULT 1,
    include_keyword_level_analysis INTEGER NOT NULL DEFAULT 1,
    include_search_term_level_analysis INTEGER NOT NULL DEFAULT 1,
    allow_keep_running INTEGER NOT NULL DEFAULT 1,
    allow_increase_bid INTEGER NOT NULL DEFAULT 1,
    allow_decrease_bid INTEGER NOT NULL DEFAULT 1,
    allow_pause_review INTEGER NOT NULL DEFAULT 1,
    allow_negative_exact INTEGER NOT NULL DEFAULT 1,
    allow_negative_phrase INTEGER NOT NULL DEFAULT 1,
    allow_move_to_exact INTEGER NOT NULL DEFAULT 1,
    allow_budget_review INTEGER NOT NULL DEFAULT 1,
    allow_data_quality_review INTEGER NOT NULL DEFAULT 1,
    allow_product_mapping_recommendations INTEGER NOT NULL DEFAULT 1,
    max_bid_increase_multiplier REAL NOT NULL DEFAULT 1.1000,
    max_bid_decrease_multiplier REAL NOT NULL DEFAULT 0.9000,
    require_high_confidence_for_pause INTEGER NOT NULL DEFAULT 1,
    require_high_confidence_for_negative_keywords INTEGER NOT NULL DEFAULT 1,
    require_min_clicks_before_action INTEGER NOT NULL DEFAULT 10,
    require_min_spend_before_action REAL NOT NULL DEFAULT 10.0000,
    target_acos_override REAL,
    min_orders_for_scaling INTEGER NOT NULL DEFAULT 2,
    min_roas_for_scaling REAL NOT NULL DEFAULT 2.0000,
    custom_system_instruction TEXT,
    custom_business_goal TEXT,
    optimization_goal TEXT NOT NULL DEFAULT 'conservative_profitability',
    brand_safety_notes TEXT,
    competitor_notes TEXT,
    product_margin_notes TEXT,
    recommendation_language TEXT NOT NULL DEFAULT 'en',
    explanation_detail TEXT NOT NULL DEFAULT 'normal' CHECK (explanation_detail IN ('simple', 'normal', 'expert')),
    show_raw_ai_reasoning_summary INTEGER NOT NULL DEFAULT 0,
    show_metric_evidence INTEGER NOT NULL DEFAULT 1,
    require_action_risk_note INTEGER NOT NULL DEFAULT 1,
    chunk_strategy TEXT NOT NULL DEFAULT 'by_product' CHECK (chunk_strategy IN ('by_product', 'by_campaign', 'by_entity_priority')),
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_workflows (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    product_id TEXT,
    monitoring_import_id TEXT REFERENCES monitoring_imports(id) ON DELETE RESTRICT,
    account_import_id TEXT REFERENCES account_imports(id) ON DELETE RESTRICT,
    upload_id TEXT REFERENCES uploads(id) ON DELETE RESTRICT,
    workflow_type TEXT NOT NULL DEFAULT 'account_import_analysis',
    status TEXT NOT NULL DEFAULT 'pending',
    current_node TEXT,
    state_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_workflow_edges (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    workflow_id TEXT REFERENCES agent_workflows(id) ON DELETE CASCADE,
    monitoring_import_id TEXT REFERENCES monitoring_imports(id) ON DELETE RESTRICT,
    source_agent_id TEXT NOT NULL,
    target_agent_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting_for_dependency',
    data_passed_summary TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE agent_run_events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL,
    agent_run_id TEXT REFERENCES ai_runs(id) ON DELETE SET NULL,
    monitoring_import_id TEXT REFERENCES monitoring_imports(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE agent_control_actions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL,
    agent_run_id TEXT REFERENCES ai_runs(id) ON DELETE SET NULL,
    monitoring_import_id TEXT REFERENCES monitoring_imports(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    actor_user_id TEXT,
    reason TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX agent_configs_workspace_idx ON agent_configs(workspace_id, product_id, agent_id);
CREATE INDEX agent_run_events_workspace_import_idx ON agent_run_events(workspace_id, monitoring_import_id, created_at);
CREATE INDEX agent_run_events_run_idx ON agent_run_events(agent_run_id, created_at);
CREATE INDEX agent_control_actions_workspace_idx ON agent_control_actions(workspace_id, agent_id, created_at DESC);

-- =============================================================================
-- Account Bulk Imports
-- =============================================================================
CREATE TABLE account_imports (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    upload_id TEXT NOT NULL,
    parse_run_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'detected' CHECK (status IN ('detected', 'needs_mapping', 'ready_for_analysis', 'processing', 'succeeded', 'failed')),
    detected_report_type TEXT NOT NULL CHECK (detected_report_type IN (
        'single_product_report', 'account_bulk_report', 'sponsored_products_search_term_report',
        'sponsored_products_targeting_report', 'sponsored_products_campaign_report',
        'bulk_sheet', 'unknown_report'
    )),
    detection_confidence TEXT NOT NULL CHECK (detection_confidence IN ('high', 'medium', 'low')),
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    processed_rows INTEGER NOT NULL DEFAULT 0 CHECK (processed_rows >= 0),
    error_rows INTEGER NOT NULL DEFAULT 0 CHECK (error_rows >= 0),
    data_quality_warnings_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id, upload_id) REFERENCES uploads(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, parse_run_id) REFERENCES upload_parse_runs(workspace_id, id) ON DELETE RESTRICT
);

CREATE TABLE account_import_entities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    account_import_id TEXT NOT NULL REFERENCES account_imports(id) ON DELETE RESTRICT,
    product_id TEXT,
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
    metrics_json TEXT NOT NULL DEFAULT '{}',
    raw_row_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT
);

CREATE TABLE product_mapping_suggestions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    account_import_id TEXT NOT NULL REFERENCES account_imports(id) ON DELETE RESTRICT,
    asin TEXT,
    sku TEXT,
    detected_product_name TEXT,
    suggested_product_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'manually_mapped')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (suggested_product_id, workspace_id) REFERENCES product_profiles(id, workspace_id) ON DELETE RESTRICT
);

CREATE INDEX account_imports_workspace_idx ON account_imports(workspace_id, created_at DESC);
CREATE INDEX account_imports_upload_idx ON account_imports(workspace_id, upload_id);
CREATE INDEX account_import_entities_import_idx ON account_import_entities(workspace_id, account_import_id, entity_type);
CREATE INDEX account_import_entities_product_idx ON account_import_entities(workspace_id, product_id);
CREATE INDEX account_import_entities_campaign_idx ON account_import_entities(workspace_id, campaign_name);
CREATE INDEX product_mapping_suggestions_import_idx ON product_mapping_suggestions(workspace_id, account_import_id, status);

-- =============================================================================
-- LangGraph Orchestration Foundation
-- =============================================================================
CREATE TABLE agent_workflow_checkpoints (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE agent_workflow_events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT,
    node_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    latency_ms INTEGER,
    provider TEXT,
    model TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE agent_tool_calls (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    agent_id TEXT,
    tool_name TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'succeeded',
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE agent_llm_calls (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    input_summary_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd REAL,
    latency_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'succeeded',
    created_at TEXT NOT NULL
);

CREATE TABLE human_approval_gates (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    gate_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'approved', 'rejected', 'edited')),
    requested_action_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    approver_user_id TEXT,
    decision_note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE INDEX agent_workflows_workspace_account_import_idx ON agent_workflows(workspace_id, account_import_id, created_at DESC);
CREATE INDEX agent_workflows_workspace_upload_idx ON agent_workflows(workspace_id, upload_id, created_at DESC);
CREATE INDEX agent_workflow_checkpoints_workflow_idx ON agent_workflow_checkpoints(workflow_id, created_at);
CREATE INDEX agent_workflow_events_workflow_idx ON agent_workflow_events(workflow_id, created_at);
CREATE INDEX agent_workflow_events_workspace_idx ON agent_workflow_events(workspace_id, created_at DESC);
CREATE INDEX agent_tool_calls_workflow_idx ON agent_tool_calls(workflow_id, created_at);
CREATE INDEX agent_llm_calls_workflow_idx ON agent_llm_calls(workflow_id, created_at);
CREATE INDEX human_approval_gates_workspace_status_idx ON human_approval_gates(workspace_id, status, created_at DESC);

-- =============================================================================
-- Competitor Cleaned Data
-- =============================================================================
CREATE TABLE competitor_uploads (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id TEXT REFERENCES product_profiles(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL CHECK (LENGTH(TRIM(original_filename)) > 0),
    storage_path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL CHECK (LENGTH(TRIM(mime_type)) > 0),
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes > 0),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'succeeded', 'failed')),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    cleaned_column_count INTEGER NOT NULL DEFAULT 0 CHECK (cleaned_column_count >= 0),
    detected_columns_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    error_message TEXT NULL,
    uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (id, workspace_id)
);

CREATE TABLE competitor_cleaned_rows (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    competitor_upload_id TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    search_term TEXT NULL,
    search_volume REAL NULL,
    competitor_rank_values_json TEXT NOT NULL DEFAULT '[]',
    raw_metrics_json TEXT NULL,
    relevance_score INTEGER NULL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 10),
    scoring_status TEXT NULL CHECK (scoring_status IN ('approved', 'rejected', 'error')),
    rejection_reason TEXT NULL,
    scored_at TEXT NULL,
    verification_status TEXT NULL CHECK (verification_status IN ('verified', 'unverified')),
    verification_result_json TEXT NULL,
    verified_at TEXT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, competitor_upload_id, row_number),
    FOREIGN KEY (competitor_upload_id, workspace_id) REFERENCES competitor_uploads(id, workspace_id) ON DELETE CASCADE
);

CREATE INDEX competitor_uploads_workspace_idx ON competitor_uploads(workspace_id, created_at DESC);
CREATE INDEX competitor_uploads_product_idx ON competitor_uploads(product_id);
CREATE INDEX competitor_cleaned_rows_upload_idx ON competitor_cleaned_rows(competitor_upload_id);
CREATE INDEX competitor_cleaned_rows_search_term_idx ON competitor_cleaned_rows(search_term);
CREATE INDEX competitor_cleaned_rows_relevance_score_idx ON competitor_cleaned_rows(relevance_score);
CREATE INDEX competitor_cleaned_rows_scoring_status_idx ON competitor_cleaned_rows(scoring_status);
CREATE INDEX competitor_cleaned_rows_verification_idx ON competitor_cleaned_rows(verification_status);

-- =============================================================================
-- Campaign Monitoring System
-- =============================================================================
CREATE TABLE campaign_locks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'locked' CHECK (status IN ('active', 'locked')),
    acos_at_lock REAL NULL,
    locked_at TEXT NOT NULL,
    locked_until TEXT NOT NULL,
    unlocked_at TEXT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, campaign_name)
);

CREATE TABLE daily_budget_snapshots (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    daily_budget REAL NOT NULL DEFAULT 10,
    spend REAL NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    orders INTEGER NOT NULL DEFAULT 0,
    sales REAL NOT NULL DEFAULT 0,
    acos REAL NULL,
    bid_multiplier REAL NOT NULL DEFAULT 1.0,
    previous_bid REAL NOT NULL DEFAULT 1.0,
    suggested_bid REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, product_id, campaign_name, snapshot_date)
);

CREATE TABLE day7_checkpoints (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    total_spend_7d REAL NOT NULL,
    total_sales_7d REAL NOT NULL,
    acos_7d REAL NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('locked', 'continue_monitoring')),
    locked_until TEXT NULL,
    evaluated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, product_id, campaign_name)
);

CREATE TABLE product_competitors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES product_profiles(id) ON DELETE CASCADE,
    competitor_name TEXT NOT NULL,
    competitor_asin TEXT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, product_id, competitor_name)
);

CREATE INDEX campaign_locks_workspace_idx ON campaign_locks(workspace_id, campaign_name);
CREATE INDEX daily_budget_snapshots_date_idx ON daily_budget_snapshots(workspace_id, product_id, snapshot_date DESC);
CREATE INDEX day7_checkpoints_workspace_idx ON day7_checkpoints(workspace_id, product_id);
CREATE INDEX product_competitors_product_idx ON product_competitors(workspace_id, product_id);

-- =============================================================================
-- Duplicate Detection & State Persistence
-- =============================================================================
CREATE TABLE data_state_hashes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, entity_type, entity_key)
);

CREATE TABLE data_version_snapshots (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    version_label TEXT NOT NULL,
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX data_state_hashes_workspace_idx ON data_state_hashes(workspace_id, entity_type);
CREATE INDEX data_version_snapshots_workspace_upload_idx ON data_version_snapshots(workspace_id, upload_id, created_at DESC);

-- =============================================================================
-- Custom Agent Builder Foundation
-- =============================================================================
CREATE TABLE custom_agent_templates (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (LENGTH(TRIM(name)) > 0),
    description TEXT NOT NULL DEFAULT '',
    task_type TEXT NOT NULL CHECK (task_type IN ('validation', 'analysis', 'decision', 'explanation', 'reporting', 'mapping', 'start', 'approval')),
    allowed_actions TEXT NOT NULL DEFAULT '["run","pause","stop","rerun","view_input","view_output","view_logs"]',
    input_dependencies TEXT NOT NULL DEFAULT '[]',
    output_type TEXT NOT NULL DEFAULT 'custom_output',
    system_prompt TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX custom_agent_templates_workspace_idx ON custom_agent_templates(workspace_id);

-- =============================================================================
-- Custom Agent Builder Runtime
-- =============================================================================
CREATE TABLE custom_agents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    role_instructions TEXT,
    model_provider TEXT NOT NULL DEFAULT 'deepseek',
    model_name TEXT NOT NULL DEFAULT 'deepseek-chat',
    temperature REAL DEFAULT 0.7 CHECK (temperature >= 0 AND temperature <= 2),
    max_tokens INTEGER DEFAULT 4096,
    memory_enabled INTEGER NOT NULL DEFAULT 0,
    memory_ttl_days INTEGER DEFAULT 30,
    output_format TEXT DEFAULT 'text',
    output_schema TEXT,
    workflow_type TEXT DEFAULT 'sequential',
    workflow_graph TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_tools (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    tool_config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    permission_level TEXT NOT NULL DEFAULT 'read' CHECK (permission_level IN ('read', 'write', 'execute', 'admin')),
    requires_approval INTEGER NOT NULL DEFAULT 0,
    rate_limit_per_day INTEGER,
    allowed_domains TEXT,
    allowed_actions TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(agent_id, tool_name)
);

CREATE TABLE knowledge_bases (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    source_type TEXT NOT NULL DEFAULT 'upload',
    file_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    embedding_provider TEXT DEFAULT 'openai',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'error')),
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE knowledge_base_files (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size_bytes INTEGER,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'error')),
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE knowledge_base_chunks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    file_id TEXT REFERENCES knowledge_base_files(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE agent_knowledge_bases (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    retrieval_priority INTEGER DEFAULT 1,
    max_chunks_per_query INTEGER DEFAULT 5,
    similarity_threshold REAL DEFAULT 0.75,
    created_at TEXT NOT NULL,
    UNIQUE(agent_id, knowledge_base_id)
);

CREATE TABLE sub_agents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    parent_agent_id TEXT NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    instructions TEXT NOT NULL,
    model_provider TEXT,
    model_name TEXT,
    tools_json TEXT NOT NULL DEFAULT '[]',
    execution_order INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    requires_approval INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_threads (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_messages (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    thread_id TEXT NOT NULL REFERENCES agent_threads(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES custom_agents(id) ON DELETE SET NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool', 'sub_agent')),
    content TEXT,
    tool_calls_json TEXT,
    tool_call_id TEXT,
    sub_agent_name TEXT,
    token_count INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE agent_memories (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    thread_id TEXT REFERENCES agent_threads(id) ON DELETE SET NULL,
    memory_type TEXT NOT NULL DEFAULT 'preference' CHECK (memory_type IN ('preference', 'fact', 'decision', 'context', 'user_info', 'project')),
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT,
    expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE custom_agent_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES custom_agents(id) ON DELETE CASCADE,
    thread_id TEXT REFERENCES agent_threads(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled', 'waiting_approval')),
    model_provider TEXT,
    model_name TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    latency_ms INTEGER,
    sub_agent_runs_json TEXT NOT NULL DEFAULT '[]',
    tool_call_count INTEGER DEFAULT 0,
    knowledge_chunks_retrieved INTEGER DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE custom_agent_run_steps (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES custom_agent_runs(id) ON DELETE CASCADE,
    agent_name TEXT,
    step_type TEXT NOT NULL CHECK (step_type IN ('planner', 'research', 'tool_call', 'knowledge_retrieval', 'llm_call', 'sub_agent', 'reviewer', 'output_format', 'approval_check')),
    step_order INTEGER NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    error_message TEXT,
    latency_ms INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE agent_secrets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    agent_id TEXT REFERENCES custom_agents(id) ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    secret_value_encrypted TEXT,
    secret_provider TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(agent_id, secret_name)
);

CREATE TABLE agent_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    config_json TEXT NOT NULL,
    is_public INTEGER NOT NULL DEFAULT 1,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX custom_agents_workspace_idx ON custom_agents(workspace_id, status, created_at DESC);
CREATE INDEX custom_agents_name_idx ON custom_agents(workspace_id, name);
CREATE INDEX agent_tools_agent_idx ON agent_tools(agent_id);
CREATE INDEX knowledge_bases_workspace_idx ON knowledge_bases(workspace_id, created_at DESC);
CREATE INDEX knowledge_base_files_kb_idx ON knowledge_base_files(knowledge_base_id, status);
CREATE INDEX knowledge_base_chunks_kb_idx ON knowledge_base_chunks(knowledge_base_id, chunk_index);
CREATE INDEX agent_knowledge_bases_agent_idx ON agent_knowledge_bases(agent_id, knowledge_base_id);
CREATE INDEX sub_agents_parent_idx ON sub_agents(parent_agent_id, execution_order);
CREATE INDEX agent_threads_agent_idx ON agent_threads(agent_id, updated_at DESC);
CREATE INDEX agent_threads_workspace_idx ON agent_threads(workspace_id, created_at DESC);
CREATE INDEX agent_messages_thread_idx ON agent_messages(thread_id, created_at);
CREATE INDEX agent_memories_agent_idx ON agent_memories(agent_id, memory_type);
CREATE INDEX custom_agent_runs_agent_idx ON custom_agent_runs(agent_id, created_at DESC);
CREATE INDEX custom_agent_runs_thread_idx ON custom_agent_runs(thread_id, created_at DESC);
CREATE INDEX custom_agent_run_steps_run_idx ON custom_agent_run_steps(run_id, step_order);
CREATE INDEX agent_secrets_agent_idx ON agent_secrets(agent_id, secret_name);

INSERT OR IGNORE INTO agent_templates (id, name, description, category, config_json) VALUES
    ('10000000-0000-4000-8000-000000000001', 'Marketing Research Agent', 'Researches competitors, market trends, and writes content briefs.', 'marketing', '{"name":"Marketing Research Agent","role_instructions":"You are an expert marketing researcher.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.7,"memory_enabled":true,"tools":["web_search"],"sub_agents":[{"name":"Research Agent","role":"Analyze competitor websites","instructions":"Search for competitor information."},{"name":"Writer Agent","role":"Create polished marketing content","instructions":"Write clear, engaging marketing content."},{"name":"Reviewer Agent","role":"Check for accuracy and quality","instructions":"Verify facts and check grammar."}],"permissions":{"requires_approval_before_email":true,"can_read_web":true,"can_write_web":false}}'),
    ('10000000-0000-4000-8000-000000000002', 'Sales Outreach Agent', 'Qualifies leads, drafts personalized emails, and manages follow-up cadences.', 'sales', '{"name":"Sales Outreach Agent","role_instructions":"You are a professional sales development representative.","model_provider":"openai","model_name":"gpt-4o","temperature":0.5,"memory_enabled":true,"tools":["crm_lookup","email_draft"],"sub_agents":[{"name":"Lead Qualifier","role":"Evaluate lead fit and priority","instructions":"Score leads based on ICP criteria."},{"name":"Email Drafter","role":"Write personalized outreach emails","instructions":"Craft compelling, personalized emails."}],"permissions":{"requires_approval_before_email":true,"can_read_crm":true,"can_send_email":false}}'),
    ('10000000-0000-4000-8000-000000000003', 'Code Review Agent', 'Reviews pull requests, suggests improvements, checks security vulnerabilities.', 'development', '{"name":"Code Review Agent","role_instructions":"You are a senior software engineer performing code reviews.","model_provider":"openai","model_name":"gpt-4o","temperature":0.3,"memory_enabled":false,"tools":["github_repo_reader"],"sub_agents":[{"name":"Security Reviewer","role":"Check for security vulnerabilities","instructions":"Scan code for OWASP top 10 vulnerabilities."},{"name":"Performance Reviewer","role":"Identify performance issues","instructions":"Check for N+1 queries and memory leaks."},{"name":"Style Reviewer","role":"Check code style and best practices."}],"permissions":{"can_read_github":true,"can_write_github":false,"can_create_pr_comment":false}}'),
    ('10000000-0000-4000-8000-000000000004', 'Customer Support Agent', 'Answers customer questions from knowledge base, drafts responses.', 'support', '{"name":"Customer Support Agent","role_instructions":"You are a helpful customer support specialist.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.4,"memory_enabled":true,"tools":["knowledge_base_search","ticket_lookup"],"sub_agents":[],"permissions":{"can_read_knowledge_base":true,"can_read_tickets":true,"can_update_tickets":false,"requires_approval_before_customer_reply":true}}'),
    ('10000000-0000-4000-8000-000000000005', 'General Research Assistant', 'Versatile research agent with web search, file analysis, and summarization.', 'general', '{"name":"General Research Assistant","role_instructions":"You are a helpful research assistant.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.7,"memory_enabled":true,"tools":["web_search"],"sub_agents":[],"permissions":{"can_read_web":true}}');

-- =============================================================================
-- Token Usage View Security (replaced with a table for SQLite)
-- =============================================================================
CREATE TABLE token_usage_log (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX token_usage_log_workspace_idx ON token_usage_log(workspace_id, created_at DESC);

-- Additional performance indexes
CREATE INDEX product_profiles_workspace_created_desc_idx ON product_profiles(workspace_id, created_at DESC);
