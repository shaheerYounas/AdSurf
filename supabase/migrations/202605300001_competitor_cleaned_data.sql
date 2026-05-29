-- Phase 1: Competitor CSV upload and cleaning
-- Stores only extracted Search Volume and Organic Rank columns from competitor research files.

create type competitor_cleaned_data_status as enum (
    'queued',
    'processing',
    'succeeded',
    'failed'
);

create table competitor_uploads (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    product_id uuid references product_profiles(id) on delete cascade,
    original_filename text not null check (length(btrim(original_filename)) > 0),
    storage_path text not null unique,
    mime_type text not null check (length(btrim(mime_type)) > 0),
    file_size_bytes integer not null check (file_size_bytes > 0),
    status competitor_cleaned_data_status not null default 'queued',
    row_count integer not null default 0 check (row_count >= 0),
    cleaned_column_count integer not null default 0 check (cleaned_column_count >= 0),
    detected_columns_json jsonb not null default '[]'::jsonb,
    warnings_json jsonb not null default '[]'::jsonb,
    error_message text null,
    uploaded_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table competitor_cleaned_rows (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    competitor_upload_id uuid not null,
    row_number integer not null check (row_number > 0),
    search_term text null,
    search_volume numeric null,
    competitor_rank_values_json jsonb not null default '[]'::jsonb,
    raw_metrics_json jsonb null,
    created_at timestamptz not null default now(),
    constraint competitor_cleaned_rows_upload_fk
        foreign key (competitor_upload_id, workspace_id)
        references competitor_uploads(id, workspace_id)
        on delete cascade,
    unique (workspace_id, competitor_upload_id, row_number)
);

create index competitor_uploads_workspace_idx
    on competitor_uploads(workspace_id, created_at desc);

create index competitor_uploads_product_idx
    on competitor_uploads(product_id);

create index competitor_cleaned_rows_upload_idx
    on competitor_cleaned_rows(competitor_upload_id);

create index competitor_cleaned_rows_search_term_idx
    on competitor_cleaned_rows(search_term);

alter table competitor_uploads enable row level security;
alter table competitor_cleaned_rows enable row level security;

create policy competitor_uploads_select_workspace_members
    on competitor_uploads for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy competitor_uploads_insert_workspace_operators
    on competitor_uploads for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy competitor_cleaned_rows_select_workspace_members
    on competitor_cleaned_rows for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy competitor_cleaned_rows_insert_workspace_operators
    on competitor_cleaned_rows for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

comment on table competitor_uploads is 'Phase 1 competitor research file uploads before scoring. Stores cleaned search volume and organic rank data.';
comment on table competitor_cleaned_rows is 'Extracted search terms with only search volume and competitor organic rank values. No relevance scoring applied yet.';