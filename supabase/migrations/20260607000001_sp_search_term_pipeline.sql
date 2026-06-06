-- SP Search Term pipeline tables
-- Adds:
--   raw_upload_rows  — exact untransformed rows for SP Search Term reports (requirement 4)
--   sp_import_health — validation report + aggregated rows per parse run

-- ---------------------------------------------------------------------------
-- raw_upload_rows: preserves raw rows exactly as received from UploadParser
-- ---------------------------------------------------------------------------

create table if not exists raw_upload_rows (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    upload_id uuid not null,
    parse_run_id uuid not null,
    row_number integer not null check (row_number > 0),
    row_hash text not null,
    raw_data jsonb not null,
    created_at timestamptz not null default now(),
    unique (parse_run_id, row_number)
);

create index raw_upload_rows_upload_idx on raw_upload_rows(workspace_id, upload_id);
create index raw_upload_rows_parse_run_idx on raw_upload_rows(parse_run_id, row_number);

alter table raw_upload_rows enable row level security;

create policy raw_upload_rows_select_workspace_members
on raw_upload_rows for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

comment on table raw_upload_rows is
    'Exact untransformed rows from SP Search Term report uploads. '
    'One row per parsed spreadsheet row before any normalization or type coercion.';

-- ---------------------------------------------------------------------------
-- sp_import_health: validation report + aggregated rows, one record per parse run
-- ---------------------------------------------------------------------------

create table if not exists sp_import_health (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    upload_id uuid not null,
    parse_run_id uuid not null unique,
    -- row counts
    total_rows integer not null default 0,
    valid_rows integer not null default 0,
    warning_rows integer not null default 0,
    error_rows integer not null default 0,
    quarantined_rows integer not null default 0,
    -- schema status
    missing_columns jsonb not null default '[]'::jsonb,
    unknown_columns jsonb not null default '[]'::jsonb,
    schema_valid boolean not null default false,
    can_generate_recommendations boolean not null default false,
    -- date / metadata
    date_range_start date,
    date_range_end date,
    currency text,
    marketplace text,
    report_type text not null default 'sponsored_products_search_term_report',
    -- issue summary and aggregated data (stored as JSONB for flexibility)
    top_issues jsonb not null default '[]'::jsonb,
    aggregated_rows_json jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index sp_import_health_upload_idx on sp_import_health(workspace_id, upload_id);

alter table sp_import_health enable row level security;

create policy sp_import_health_select_workspace_members
on sp_import_health for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

comment on table sp_import_health is
    'Validation report and aggregated rows for SP Search Term report imports. '
    'One record per upload parse run. Aggregated rows are recalculated from raw totals '
    'and gated behind schema validity for recommendation generation.';
