create table campaign_plans (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    product_id uuid not null,
    approved_keyword_set_id uuid not null,
    version integer not null check (version > 0),
    status text not null check (status in ('generated', 'approved', 'rejected', 'superseded')),
    rule_version_id text not null,
    plan_json jsonb not null,
    created_by uuid not null,
    approved_by uuid,
    approval_note text,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_plans_product_fk
        foreign key (product_id, workspace_id)
        references product_profiles(id, workspace_id)
        on delete restrict,
    constraint campaign_plans_keyword_set_fk
        foreign key (approved_keyword_set_id, workspace_id, product_id)
        references approved_keyword_sets(id, workspace_id, product_id)
        on delete restrict,
    unique (workspace_id, product_id, version)
);

create table bulk_exports (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    product_id uuid not null,
    campaign_plan_id uuid not null,
    status text not null check (status in ('approved', 'failed')),
    storage_path text not null unique,
    original_filename text not null check (length(btrim(original_filename)) > 0),
    rows_json jsonb not null,
    approved_by uuid not null,
    approval_note text not null check (length(btrim(approval_note)) > 0),
    approved_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint bulk_exports_plan_fk
        foreign key (campaign_plan_id)
        references campaign_plans(id)
        on delete restrict,
    constraint bulk_exports_product_fk
        foreign key (product_id, workspace_id)
        references product_profiles(id, workspace_id)
        on delete restrict
);

create index campaign_plans_workspace_product_idx on campaign_plans(workspace_id, product_id);
create index campaign_plans_keyword_set_idx on campaign_plans(approved_keyword_set_id);
create index bulk_exports_workspace_product_idx on bulk_exports(workspace_id, product_id);
create index bulk_exports_plan_idx on bulk_exports(campaign_plan_id);

alter table campaign_plans enable row level security;
alter table bulk_exports enable row level security;

create policy campaign_plans_select_workspace_members
    on campaign_plans
    for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy campaign_plans_insert_workspace_operators
    on campaign_plans
    for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy campaign_plans_update_workspace_operators
    on campaign_plans
    for update
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy bulk_exports_select_workspace_members
    on bulk_exports
    for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy bulk_exports_insert_workspace_operators
    on bulk_exports
    for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
