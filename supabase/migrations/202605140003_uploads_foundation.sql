create type upload_status as enum (
    'initialized',
    'uploaded',
    'queued_for_processing',
    'processing',
    'processed',
    'failed',
    'cancelled'
);

create type upload_source_type as enum (
    'competitor_keyword_research'
);

create table uploads (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid not null references product_profiles(id) on delete restrict,
    uploaded_by uuid,
    original_filename text not null,
    storage_path text not null unique,
    mime_type text not null,
    file_size_bytes bigint check (file_size_bytes is null or file_size_bytes > 0),
    status upload_status not null default 'initialized',
    source_type upload_source_type not null,
    idempotency_key text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    confirmed_at timestamptz,
    unique (workspace_id, idempotency_key)
);

create index uploads_workspace_id_idx on uploads(workspace_id);
create index uploads_product_id_idx on uploads(product_id);
create index uploads_status_idx on uploads(status);
create index uploads_created_at_idx on uploads(created_at);
create index uploads_idempotency_key_idx on uploads(idempotency_key);

alter table uploads enable row level security;

comment on table uploads is 'Raw upload metadata only. File parsing and column mapping are intentionally deferred.';

create policy uploads_select_workspace_members
on uploads for select
to authenticated
using (public.current_user_is_workspace_member(workspace_id));

create policy uploads_insert_workspace_writers
on uploads for insert
to authenticated
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy uploads_update_workspace_writers
on uploads for update
to authenticated
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

comment on policy uploads_select_workspace_members on uploads is
    'Uses SECURITY DEFINER helper to avoid recursive workspace_members policy checks.';
comment on policy uploads_insert_workspace_writers on uploads is
    'Only owner/admin/analyst can initialize uploads; helper avoids recursive RLS.';
comment on policy uploads_update_workspace_writers on uploads is
    'Only owner/admin/analyst can confirm or update upload lifecycle state; helper avoids recursive RLS.';
