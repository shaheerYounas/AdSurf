create type upload_column_profile_status as enum (
    'generated',
    'failed'
);

create type upload_column_inferred_data_type as enum (
    'text',
    'integer',
    'decimal',
    'date',
    'boolean',
    'unknown'
);

create type upload_column_mapping_status as enum (
    'draft',
    'valid',
    'invalid',
    'approved',
    'superseded'
);

create type upload_column_mapping_type as enum (
    'manual'
);

create table upload_column_profiles (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    product_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null,
    status upload_column_profile_status not null,
    total_columns integer not null default 0 check (total_columns >= 0),
    total_rows_sampled integer not null default 0 check (total_rows_sampled >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (parse_run_id),
    constraint upload_column_profiles_scope_identity_key
        unique (id, workspace_id, product_id, upload_id, parse_run_id),
    constraint upload_column_profiles_parse_run_scope_fk
        foreign key (parse_run_id, workspace_id, product_id, upload_id)
        references upload_parse_runs(id, workspace_id, product_id, upload_id)
        on delete restrict
);

create table upload_column_profile_columns (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    product_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null,
    column_profile_id uuid not null,
    original_column_name text not null,
    normalized_column_name text not null,
    column_index integer not null check (column_index >= 0),
    non_null_count integer not null default 0 check (non_null_count >= 0),
    sample_values_json jsonb not null default '[]'::jsonb,
    inferred_data_type upload_column_inferred_data_type not null,
    created_at timestamptz not null default now(),
    unique (column_profile_id, column_index),
    unique (column_profile_id, original_column_name),
    constraint upload_column_profile_columns_profile_scope_fk
        foreign key (column_profile_id, workspace_id, product_id, upload_id, parse_run_id)
        references upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id)
        on delete restrict
);

create table upload_column_mappings (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    product_id uuid not null,
    upload_id uuid not null,
    parse_run_id uuid not null,
    column_profile_id uuid not null,
    status upload_column_mapping_status not null,
    mapping_version integer not null check (mapping_version > 0),
    mapping_type upload_column_mapping_type not null default 'manual',
    mapping_json jsonb not null,
    validation_errors_json jsonb not null default '[]'::jsonb,
    created_by uuid,
    created_at timestamptz not null default now(),
    approved_at timestamptz,
    unique (column_profile_id, mapping_version),
    constraint upload_column_mappings_profile_scope_fk
        foreign key (column_profile_id, workspace_id, product_id, upload_id, parse_run_id)
        references upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id)
        on delete restrict
);

create index upload_column_profiles_workspace_upload_idx
    on upload_column_profiles(workspace_id, upload_id, created_at desc);
create index upload_column_profile_columns_profile_idx
    on upload_column_profile_columns(column_profile_id, column_index);
create index upload_column_mappings_profile_idx
    on upload_column_mappings(column_profile_id, mapping_version desc);
create index upload_column_mappings_workspace_upload_idx
    on upload_column_mappings(workspace_id, upload_id, created_at desc);

alter table upload_column_profiles enable row level security;
alter table upload_column_profile_columns enable row level security;
alter table upload_column_mappings enable row level security;

create policy upload_column_profiles_select_workspace_members
on upload_column_profiles for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

create policy upload_column_profile_columns_select_workspace_members
on upload_column_profile_columns for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

create policy upload_column_mappings_select_workspace_members
on upload_column_mappings for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

create policy upload_column_mappings_insert_workspace_writers
on upload_column_mappings for insert
to authenticated
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy upload_column_mappings_update_workspace_writers
on upload_column_mappings for update
to authenticated
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

comment on table upload_column_profiles is 'Deterministic parsed-column discovery only. Batch 5 does not perform semantic AI mapping or scoring.';
comment on table upload_column_profile_columns is 'Column names, samples, and inferred data types for manual mapping.';
comment on table upload_column_mappings is 'Manual column mapping snapshots for later scoring. Approval does not trigger scoring in Batch 5.';
