alter table workspaces enable row level security;
alter table workspace_members enable row level security;
alter table product_profiles enable row level security;
alter table audit_logs enable row level security;
alter table rule_versions enable row level security;
alter table job_queue enable row level security;
alter table outbox_events enable row level security;

-- RLS policy expressions must not query workspace_members from the
-- workspace_members policy itself. These SECURITY DEFINER helpers centralize
-- membership checks and bypass table RLS safely with a locked search_path.
create or replace function public.current_user_is_workspace_member(workspace_uuid uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from workspace_members wm
    where wm.workspace_id = workspace_uuid
      and wm.user_id = auth.uid()
      and wm.status = 'active'
  );
$$;

comment on function public.current_user_is_workspace_member(uuid)
  is 'Non-recursive RLS helper for active workspace membership checks.';

create or replace function public.current_user_has_workspace_role(workspace_uuid uuid, allowed_roles text[])
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from workspace_members wm
    where wm.workspace_id = workspace_uuid
      and wm.user_id = auth.uid()
      and wm.status = 'active'
      and wm.role::text = any(allowed_roles)
  );
$$;

comment on function public.current_user_has_workspace_role(uuid, text[])
  is 'Non-recursive RLS helper for active workspace role checks.';

create policy workspaces_select_for_members
  on workspaces
  for select
  to authenticated
  using (public.current_user_is_workspace_member(id));

-- This policy is intentionally self-row only. Workspace-wide membership
-- checks use SECURITY DEFINER helpers above to avoid recursive RLS evaluation.
create policy workspace_members_select_own_memberships
  on workspace_members
  for select
  to authenticated
  using (user_id = auth.uid() and status = 'active');

create policy product_profiles_select_for_workspace_members
  on product_profiles
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));

create policy product_profiles_insert_for_workspace_writers
  on product_profiles
  for insert
  to authenticated
  with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy product_profiles_update_for_workspace_writers
  on product_profiles
  for update
  to authenticated
  using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
  with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy audit_logs_select_for_workspace_members
  on audit_logs
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));

-- Rule versions are global deterministic configuration, not workspace-owned
-- customer data, so authenticated read access is intentionally broad.
create policy rule_versions_select_for_authenticated
  on rule_versions
  for select
  to authenticated
  using (true);

create policy job_queue_select_for_workspace_members
  on job_queue
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));

create policy outbox_events_select_for_workspace_members
  on outbox_events
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));
