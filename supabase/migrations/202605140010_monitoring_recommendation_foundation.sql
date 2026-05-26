alter type upload_source_type add value if not exists 'amazon_ads_sp_search_term_report';

create type monitoring_import_status as enum ('queued', 'processing', 'succeeded', 'failed');
create type recommendation_status as enum ('pending_approval', 'approved', 'rejected', 'superseded');
create type recommendation_type as enum ('increase_bid', 'decrease_bid', 'pause_review', 'negative_keyword_review', 'watch_lock');
create type recommendation_priority as enum ('high', 'medium', 'low');

create table monitoring_imports (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null,
    report_type text not null check (report_type = 'sponsored_products_search_term'),
    status monitoring_import_status not null default 'queued',
    date_range_start text,
    date_range_end text,
    total_rows integer not null default 0,
    processed_rows integer not null default 0,
    error_rows integer not null default 0,
    data_quality_warnings_json jsonb not null default '[]'::jsonb,
    created_by uuid not null,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint monitoring_imports_product_fk
        foreign key (product_id, workspace_id)
        references product_profiles(id, workspace_id)
        on delete restrict,
    constraint monitoring_imports_upload_fk
        foreign key (workspace_id, product_id, upload_id)
        references uploads(workspace_id, product_id, id)
        on delete restrict,
    constraint monitoring_imports_parse_run_fk
        foreign key (parse_run_id, workspace_id, product_id, upload_id)
        references upload_parse_runs(id, workspace_id, product_id, upload_id)
        on delete restrict
);

create table monitoring_snapshots (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid not null,
    monitoring_import_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null,
    source_row_id uuid not null,
    campaign_name text not null,
    ad_group_name text not null,
    targeting text not null,
    match_type text,
    customer_search_term text not null,
    start_date text,
    end_date text,
    impressions integer not null default 0,
    clicks integer not null default 0,
    spend numeric(12,4) not null default 0,
    sales numeric(12,4) not null default 0,
    orders integer not null default 0,
    units integer,
    cpc numeric(12,4),
    ctr numeric(8,4),
    cvr numeric(8,4),
    acos numeric(8,4),
    roas numeric(12,4),
    raw_metrics_json jsonb not null,
    created_at timestamptz not null default now(),
    constraint monitoring_snapshots_import_fk
        foreign key (monitoring_import_id)
        references monitoring_imports(id)
        on delete restrict,
    constraint monitoring_snapshots_scope_fk
        foreign key (workspace_id, product_id, upload_id)
        references uploads(workspace_id, product_id, id)
        on delete restrict,
    constraint monitoring_snapshots_source_row_fk
        foreign key (source_row_id)
        references upload_parsed_rows(id)
        on delete restrict
);

create table recommendations (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid not null,
    monitoring_import_id uuid not null,
    snapshot_id uuid not null,
    recommendation_type recommendation_type not null,
    status recommendation_status not null default 'pending_approval',
    priority recommendation_priority not null,
    rule_version_id text not null,
    rule_name text not null,
    campaign_name text not null,
    ad_group_name text not null,
    targeting text not null,
    customer_search_term text not null,
    input_metrics_json jsonb not null,
    proposed_action_json jsonb not null,
    explanation_json jsonb not null,
    decided_by uuid,
    decision_note text,
    decided_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint recommendations_product_fk
        foreign key (product_id, workspace_id)
        references product_profiles(id, workspace_id)
        on delete restrict,
    constraint recommendations_import_fk
        foreign key (monitoring_import_id)
        references monitoring_imports(id)
        on delete restrict,
    constraint recommendations_snapshot_fk
        foreign key (snapshot_id)
        references monitoring_snapshots(id)
        on delete restrict
);

create table recommendation_decisions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    recommendation_id uuid not null references recommendations(id) on delete restrict,
    decision recommendation_status not null check (decision in ('approved', 'rejected')),
    actor_user_id uuid not null,
    note text not null check (length(btrim(note)) > 0),
    created_at timestamptz not null default now()
);

create table ai_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_name text not null,
    provider text not null,
    model text not null,
    schema_version text not null,
    input_hash text not null,
    output_json jsonb not null,
    status text not null,
    latency_ms integer not null default 0,
    created_at timestamptz not null default now()
);

create index monitoring_imports_workspace_product_idx on monitoring_imports(workspace_id, product_id, created_at desc);
create index monitoring_snapshots_workspace_product_idx on monitoring_snapshots(workspace_id, product_id);
create index recommendations_workspace_status_idx on recommendations(workspace_id, status, priority);
create index recommendations_workspace_type_idx on recommendations(workspace_id, recommendation_type);
create index recommendation_decisions_workspace_idx on recommendation_decisions(workspace_id, recommendation_id);
create index ai_runs_workspace_agent_idx on ai_runs(workspace_id, agent_name, created_at desc);

alter table monitoring_imports enable row level security;
alter table monitoring_snapshots enable row level security;
alter table recommendations enable row level security;
alter table recommendation_decisions enable row level security;
alter table ai_runs enable row level security;

create policy monitoring_imports_select_workspace_members on monitoring_imports for select
using (public.current_user_is_workspace_member(workspace_id));
create policy monitoring_imports_insert_workspace_operators on monitoring_imports for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy monitoring_imports_update_workspace_operators on monitoring_imports for update
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy monitoring_snapshots_select_workspace_members on monitoring_snapshots for select
using (public.current_user_is_workspace_member(workspace_id));
create policy monitoring_snapshots_insert_workspace_operators on monitoring_snapshots for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy recommendations_select_workspace_members on recommendations for select
using (public.current_user_is_workspace_member(workspace_id));
create policy recommendations_insert_workspace_operators on recommendations for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy recommendations_update_workspace_operators on recommendations for update
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst', 'approver']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst', 'approver']));

create policy recommendation_decisions_select_workspace_members on recommendation_decisions for select
using (public.current_user_is_workspace_member(workspace_id));
create policy recommendation_decisions_insert_workspace_operators on recommendation_decisions for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst', 'approver']));

create policy ai_runs_select_workspace_members on ai_runs for select
using (public.current_user_is_workspace_member(workspace_id));
create policy ai_runs_insert_workspace_operators on ai_runs for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
