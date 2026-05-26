create type keyword_candidate_override_action as enum ('approve', 'reject');
create type reviewed_keyword_status as enum ('approved', 'rejected');
create type approved_keyword_set_status as enum ('created', 'locked', 'superseded');

alter table keyword_candidates
    add constraint keyword_candidates_review_scope_identity_key
    unique (id, workspace_id, product_id, scoring_run_id);

alter table keyword_scoring_runs
    add constraint keyword_scoring_runs_review_scope_identity_key
    unique (id, workspace_id, product_id, column_mapping_id);

create table keyword_candidate_overrides (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    product_id uuid not null,
    scoring_run_id uuid not null,
    keyword_candidate_id uuid not null,
    override_action keyword_candidate_override_action not null,
    original_scoring_status keyword_candidate_status not null check (original_scoring_status in ('approved', 'rejected')),
    new_status reviewed_keyword_status not null,
    reason text not null check (length(btrim(reason)) > 0),
    created_by uuid not null,
    created_at timestamptz not null default now(),
    constraint keyword_candidate_overrides_candidate_scope_fk
        foreign key (keyword_candidate_id, workspace_id, product_id, scoring_run_id)
        references keyword_candidates(id, workspace_id, product_id, scoring_run_id)
        on delete restrict,
    constraint keyword_candidate_overrides_action_status_check
        check (
            (override_action = 'approve' and new_status = 'approved')
            or (override_action = 'reject' and new_status = 'rejected')
        ),
    unique (keyword_candidate_id)
);

create table approved_keyword_sets (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    product_id uuid not null,
    scoring_run_id uuid not null,
    column_mapping_id uuid not null,
    name text not null check (length(btrim(name)) > 0),
    status approved_keyword_set_status not null default 'locked',
    keyword_count integer not null default 0 check (keyword_count >= 0),
    created_by uuid not null,
    created_at timestamptz not null default now(),
    approved_at timestamptz,
    constraint approved_keyword_sets_scoring_run_scope_fk
        foreign key (scoring_run_id, workspace_id, product_id, column_mapping_id)
        references keyword_scoring_runs(id, workspace_id, product_id, column_mapping_id)
        on delete restrict,
    constraint approved_keyword_sets_scope_identity_key
        unique (id, workspace_id, product_id)
);

create table approved_keyword_set_items (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    product_id uuid not null,
    approved_keyword_set_id uuid not null,
    scoring_run_id uuid not null,
    keyword_candidate_id uuid not null,
    search_term text not null check (length(btrim(search_term)) > 0),
    search_volume numeric(18,4),
    relevance_score integer not null check (relevance_score between 0 and 10),
    source_status keyword_candidate_status not null,
    final_status reviewed_keyword_status not null default 'approved' check (final_status = 'approved'),
    override_id uuid,
    created_at timestamptz not null default now(),
    constraint approved_keyword_set_items_set_scope_fk
        foreign key (approved_keyword_set_id, workspace_id, product_id)
        references approved_keyword_sets(id, workspace_id, product_id)
        on delete restrict,
    constraint approved_keyword_set_items_candidate_scope_fk
        foreign key (keyword_candidate_id, workspace_id, product_id, scoring_run_id)
        references keyword_candidates(id, workspace_id, product_id, scoring_run_id)
        on delete restrict,
    constraint approved_keyword_set_items_override_fk
        foreign key (override_id)
        references keyword_candidate_overrides(id)
        on delete restrict,
    unique (approved_keyword_set_id, keyword_candidate_id)
);

create index keyword_candidate_overrides_workspace_product_idx on keyword_candidate_overrides(workspace_id, product_id);
create index keyword_candidate_overrides_scoring_run_idx on keyword_candidate_overrides(scoring_run_id);
create index approved_keyword_sets_workspace_product_idx on approved_keyword_sets(workspace_id, product_id);
create index approved_keyword_sets_scoring_run_idx on approved_keyword_sets(scoring_run_id);
create index approved_keyword_set_items_set_idx on approved_keyword_set_items(approved_keyword_set_id);
create index approved_keyword_set_items_scoring_run_idx on approved_keyword_set_items(scoring_run_id);
create index approved_keyword_set_items_search_term_idx on approved_keyword_set_items(search_term);

alter table keyword_candidate_overrides enable row level security;
alter table approved_keyword_sets enable row level security;
alter table approved_keyword_set_items enable row level security;

create policy keyword_candidate_overrides_select_workspace_members
    on keyword_candidate_overrides
    for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy keyword_candidate_overrides_insert_workspace_operators
    on keyword_candidate_overrides
    for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy approved_keyword_sets_select_workspace_members
    on approved_keyword_sets
    for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy approved_keyword_sets_insert_workspace_operators
    on approved_keyword_sets
    for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy approved_keyword_set_items_select_workspace_members
    on approved_keyword_set_items
    for select
    using (public.current_user_is_workspace_member(workspace_id));

create policy approved_keyword_set_items_insert_workspace_operators
    on approved_keyword_set_items
    for insert
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
