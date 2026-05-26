create type upload_parse_status as enum (
    'running',
    'succeeded',
    'failed'
);

alter table uploads
add constraint uploads_workspace_product_id_key unique (workspace_id, product_id, id);

create table upload_parse_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid not null,
    upload_id uuid not null,
    job_id uuid not null unique references job_queue(id) on delete restrict,
    status upload_parse_status not null,
    parser_version text not null,
    original_filename text not null,
    storage_path text not null,
    detected_file_type text not null,
    detected_sheet_names jsonb not null default '[]'::jsonb,
    selected_sheet_name text,
    total_rows integer not null default 0 check (total_rows >= 0),
    total_columns integer not null default 0 check (total_columns >= 0),
    parsed_rows_count integer not null default 0 check (parsed_rows_count >= 0),
    error_rows_count integer not null default 0 check (error_rows_count >= 0),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    error_message text,
    constraint upload_parse_runs_scope_identity_key unique (id, workspace_id, product_id, upload_id),
    constraint upload_parse_runs_upload_fk
        foreign key (workspace_id, product_id, upload_id)
        references uploads(workspace_id, product_id, id)
        on delete restrict
);

create table upload_parsed_rows (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    product_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null references upload_parse_runs(id) on delete restrict,
    row_number integer not null check (row_number > 0),
    row_data_json jsonb not null,
    row_hash text not null,
    created_at timestamptz not null default now(),
    unique (parse_run_id, row_number),
    constraint upload_parsed_rows_parse_run_scope_fk
        foreign key (parse_run_id, workspace_id, product_id, upload_id)
        references upload_parse_runs(id, workspace_id, product_id, upload_id)
        on delete restrict,
    constraint upload_parsed_rows_upload_fk
        foreign key (workspace_id, product_id, upload_id)
        references uploads(workspace_id, product_id, id)
        on delete restrict
);

create table upload_parse_errors (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    product_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null references upload_parse_runs(id) on delete restrict,
    row_number integer check (row_number is null or row_number > 0),
    error_code text not null,
    error_message text not null,
    raw_value_json jsonb,
    created_at timestamptz not null default now(),
    constraint upload_parse_errors_parse_run_scope_fk
        foreign key (parse_run_id, workspace_id, product_id, upload_id)
        references upload_parse_runs(id, workspace_id, product_id, upload_id)
        on delete restrict,
    constraint upload_parse_errors_upload_fk
        foreign key (workspace_id, product_id, upload_id)
        references uploads(workspace_id, product_id, id)
        on delete restrict
);

create index upload_parse_runs_workspace_upload_idx on upload_parse_runs(workspace_id, upload_id, created_at desc);
create index upload_parsed_rows_parse_run_idx on upload_parsed_rows(parse_run_id, row_number);
create index upload_parse_errors_parse_run_idx on upload_parse_errors(parse_run_id, row_number);

alter table upload_parse_runs enable row level security;
alter table upload_parsed_rows enable row level security;
alter table upload_parse_errors enable row level security;

create policy upload_parse_runs_select_workspace_members
on upload_parse_runs for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

create policy upload_parsed_rows_select_workspace_members
on upload_parsed_rows for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

create policy upload_parse_errors_select_workspace_members
on upload_parse_errors for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

comment on table upload_parse_runs is 'Metadata for deterministic file parsing only. Batch 4 does not perform column mapping or scoring.';
comment on table upload_parsed_rows is 'Parsed spreadsheet/CSV rows stored as untrusted JSON data.';
comment on table upload_parse_errors is 'Row-level or file-level parse errors captured without interpreting spreadsheet content.';
