from pathlib import Path


def test_initial_foundation_migration_exists_with_required_tables_and_roles() -> None:
    migration = Path("supabase/migrations/202605140001_initial_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["workspaces", "workspace_members", "product_profiles", "audit_logs", "rule_versions", "job_queue"]:
        assert f"create table {table}" in sql

    for role in ["owner", "admin", "analyst", "approver", "viewer"]:
        assert f"'{role}'" in sql

    assert "numeric(12,4)" in sql
    assert "workspace_id uuid not null references workspaces(id)" in sql


def test_foundation_rls_migration_exists_without_broad_public_policies() -> None:
    migration = Path("supabase/migrations/202605140002_foundation_rls.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["workspaces", "workspace_members", "product_profiles", "audit_logs", "rule_versions", "job_queue", "outbox_events"]:
        assert f"alter table {table} enable row level security" in sql

    assert "to public" not in sql
    assert "wm.user_id = auth.uid()" in sql
    assert "security definer" in sql
    assert "set search_path = public, pg_temp" in sql
    assert "public.current_user_is_workspace_member" in sql
    assert "public.current_user_has_workspace_role" in sql
    assert "workspace_members_select_own_memberships" in sql
    assert "workspace_members.workspace_id" not in sql


def test_uploads_migration_adds_scoped_metadata_and_rls() -> None:
    migration = Path("supabase/migrations/202605140003_uploads_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    assert "create table uploads" in sql
    for column in [
        "workspace_id uuid not null references workspaces(id)",
        "product_id uuid not null references product_profiles(id)",
        "storage_path text not null unique",
        "unique (workspace_id, idempotency_key)",
        "file_size_bytes bigint check",
    ]:
        assert column in sql
    for status in ["initialized", "queued_for_processing", "processed", "cancelled"]:
        assert f"'{status}'" in sql

    assert "alter table uploads enable row level security" in sql
    assert "to public" not in sql
    assert "public.current_user_is_workspace_member(workspace_id)" in sql
    assert "public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst'])" in sql
    assert "disable row level security" not in sql


def test_upload_integrity_migration_enforces_product_workspace_match() -> None:
    migration = Path("supabase/migrations/202605140004_upload_integrity_hardening.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    assert "unique (id, workspace_id)" in sql
    assert "foreign key (product_id, workspace_id)" in sql
    assert "references product_profiles(id, workspace_id)" in sql
    assert "uploads_product_workspace_fk" in sql
    assert "to public" not in sql
    assert "disable row level security" not in sql


def test_upload_parse_migration_adds_read_only_workspace_scoped_tables() -> None:
    migration = Path("supabase/migrations/202605140005_upload_parse_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["upload_parse_runs", "upload_parsed_rows", "upload_parse_errors"]:
        assert f"create table {table}" in sql
        assert f"alter table {table} enable row level security" in sql

    assert "foreign key (workspace_id, product_id, upload_id)" in sql
    assert "constraint upload_parse_runs_scope_identity_key unique (id, workspace_id, product_id, upload_id)" in sql
    assert "constraint upload_parsed_rows_parse_run_scope_fk" in sql
    assert "foreign key (parse_run_id, workspace_id, product_id, upload_id)" in sql
    assert "references upload_parse_runs(id, workspace_id, product_id, upload_id)" in sql
    assert "constraint upload_parse_errors_parse_run_scope_fk" in sql
    assert "unique (parse_run_id, row_number)" in sql
    assert "row_data_json jsonb not null" in sql
    assert "row_hash text not null" in sql
    assert "error_code text not null" in sql
    assert "for insert" not in sql
    assert "for update" not in sql
    assert "to public" not in sql
    assert "public.current_user_is_workspace_member(workspace_id)" in sql


def test_column_mapping_migration_adds_manual_mapping_tables_and_rls() -> None:
    migration = Path("supabase/migrations/202605140006_column_mapping_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["upload_column_profiles", "upload_column_profile_columns", "upload_column_mappings"]:
        assert f"create table {table}" in sql
        assert f"alter table {table} enable row level security" in sql

    assert "create type upload_column_mapping_type" in sql
    assert "'manual'" in sql
    assert "unique (parse_run_id)" in sql
    assert "constraint upload_column_profiles_parse_run_scope_fk" in sql
    assert "foreign key (parse_run_id, workspace_id, product_id, upload_id)" in sql
    assert "references upload_parse_runs(id, workspace_id, product_id, upload_id)" in sql
    assert "constraint upload_column_profile_columns_profile_scope_fk" in sql
    assert "foreign key (column_profile_id, workspace_id, product_id, upload_id, parse_run_id)" in sql
    assert "references upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id)" in sql
    assert "constraint upload_column_mappings_profile_scope_fk" in sql
    assert "unique (column_profile_id, mapping_version)" in sql
    assert "public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst'])" in sql
    assert "to public" not in sql
    assert "disable row level security" not in sql


def test_keyword_scoring_migration_adds_scoped_tables_and_rls() -> None:
    migration = Path("supabase/migrations/202605140007_keyword_scoring_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["keyword_scoring_runs", "keyword_candidates"]:
        assert f"create table {table}" in sql
        assert f"alter table {table} enable row level security" in sql

    assert "create type keyword_scoring_run_status" in sql
    assert "create type keyword_candidate_status" in sql
    assert "upload_column_mappings_scope_identity_key" in sql
    assert "unique (column_mapping_id, scoring_version)" in sql
    assert "unique (workspace_id, idempotency_key)" in sql
    assert "constraint keyword_scoring_runs_mapping_scope_fk" in sql
    assert "foreign key (column_mapping_id, workspace_id, product_id, upload_id, parse_run_id)" in sql
    assert "references upload_column_mappings(id, workspace_id, product_id, upload_id, parse_run_id)" in sql
    assert "constraint keyword_candidates_scoring_run_scope_fk" in sql
    assert "references keyword_scoring_runs(id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)" in sql
    assert "keyword_candidates_search_term_required_for_scored" in sql
    for index in [
        "keyword_candidates_workspace_product_idx",
        "keyword_candidates_upload_idx",
        "keyword_candidates_scoring_run_idx",
        "keyword_candidates_scoring_status_idx",
        "keyword_candidates_relevance_score_idx",
        "keyword_candidates_search_term_idx",
    ]:
        assert index in sql
    assert "to public" not in sql
    assert "disable row level security" not in sql


def test_keyword_review_migration_adds_override_and_snapshot_tables() -> None:
    migration = Path("supabase/migrations/202605140008_keyword_review_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["keyword_candidate_overrides", "approved_keyword_sets", "approved_keyword_set_items"]:
        assert f"create table {table}" in sql
        assert f"alter table {table} enable row level security" in sql

    assert "create type keyword_candidate_override_action" in sql
    assert "create type reviewed_keyword_status" in sql
    assert "create type approved_keyword_set_status" in sql
    assert "keyword_candidates_review_scope_identity_key" in sql
    assert "unique (id, workspace_id, product_id, scoring_run_id)" in sql
    assert "keyword_scoring_runs_review_scope_identity_key" in sql
    assert "unique (id, workspace_id, product_id, column_mapping_id)" in sql
    assert "constraint keyword_candidate_overrides_candidate_scope_fk" in sql
    assert "foreign key (keyword_candidate_id, workspace_id, product_id, scoring_run_id)" in sql
    assert "references keyword_candidates(id, workspace_id, product_id, scoring_run_id)" in sql
    assert "unique (keyword_candidate_id)" in sql
    assert "reason text not null check (length(btrim(reason)) > 0)" in sql
    assert "constraint approved_keyword_sets_scoring_run_scope_fk" in sql
    assert "foreign key (scoring_run_id, workspace_id, product_id, column_mapping_id)" in sql
    assert "references keyword_scoring_runs(id, workspace_id, product_id, column_mapping_id)" in sql
    assert "constraint approved_keyword_set_items_set_scope_fk" in sql
    assert "constraint approved_keyword_set_items_candidate_scope_fk" in sql
    assert "final_status reviewed_keyword_status not null default 'approved' check (final_status = 'approved')" in sql
    assert "public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst'])" in sql
    assert "to public" not in sql
    assert "disable row level security" not in sql


def test_monitoring_recommendation_migration_adds_agent_tables_and_rls() -> None:
    migration = Path("supabase/migrations/202605140010_monitoring_recommendation_foundation.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for table in ["monitoring_imports", "monitoring_snapshots", "recommendations", "recommendation_decisions", "ai_runs"]:
        assert f"create table {table}" in sql
        assert f"alter table {table} enable row level security" in sql

    assert "alter type upload_source_type add value if not exists 'amazon_ads_sp_search_term_report'" in sql
    assert "create type recommendation_type" in sql
    assert "'increase_bid'" in sql
    assert "'decrease_bid'" in sql
    assert "'pause_review'" in sql
    assert "'watch_lock'" in sql
    assert "input_metrics_json jsonb not null" in sql
    assert "proposed_action_json jsonb not null" in sql
    assert "explanation_json jsonb not null" in sql
    assert "provider text not null" in sql
    assert "schema_version text not null" in sql
    assert "public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst'])" in sql
    assert "public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst', 'approver'])" in sql
    assert "to public" not in sql
    assert "disable row level security" not in sql


def test_monitoring_phase_1_migration_adds_recommendation_types_and_evidence_json() -> None:
    migration = Path("supabase/migrations/202605260001_monitoring_phase_1_recommendations.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for recommendation_type in [
        "keep_running",
        "add_negative_exact",
        "add_negative_phrase",
        "move_to_exact",
        "data_quality_review",
        "budget_review",
    ]:
        assert f"'{recommendation_type}'" in sql

    assert "alter type recommendation_priority add value if not exists 'critical'" in sql
    assert "alter type recommendation_status add value if not exists 'pending'" in sql
    assert "add column if not exists entity_type text not null default 'search_term'" in sql
    assert "add column if not exists confidence text not null default 'medium'" in sql
    assert "add column if not exists current_metric_snapshot_json jsonb not null default '{}'::jsonb" in sql
    assert "add column if not exists evidence_json jsonb not null default '{}'::jsonb" in sql
    assert "alter table ai_runs" in sql
    assert "add column if not exists product_id uuid" in sql
    assert "Amazon Ads mutations" in sql


def test_dashboard_performance_indexes_migration_exists() -> None:
    migration = Path("supabase/migrations/202605260002_dashboard_performance_indexes.sql")

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8")

    for index in [
        "product_profiles_workspace_created_desc_idx",
        "uploads_workspace_created_desc_idx",
        "uploads_workspace_status_created_desc_idx",
        "recommendations_workspace_product_status_priority_created_idx",
        "recommendations_workspace_priority_created_idx",
        "ai_runs_workspace_product_agent_created_idx",
    ]:
        assert f"create index if not exists {index}" in sql
