alter table agent_workflows
    add column if not exists account_import_id uuid references account_imports(id) on delete restrict,
    add column if not exists upload_id uuid references uploads(id) on delete restrict,
    add column if not exists workflow_type text not null default 'account_import_analysis',
    add column if not exists current_node text,
    add column if not exists state_json jsonb not null default '{}'::jsonb,
    add column if not exists error_json jsonb not null default '{}'::jsonb,
    add column if not exists created_by uuid,
    add column if not exists completed_at timestamptz;

create table if not exists agent_workflow_checkpoints (
    id uuid primary key default gen_random_uuid(),
    workflow_id uuid not null references agent_workflows(id) on delete cascade,
    node_name text not null,
    state_json jsonb not null default '{}'::jsonb,
    status text not null,
    created_at timestamptz not null default now()
);

create table if not exists agent_workflow_events (
    id uuid primary key default gen_random_uuid(),
    workflow_id uuid not null references agent_workflows(id) on delete cascade,
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id text,
    node_name text not null,
    event_type text not null,
    message text not null,
    metadata_json jsonb not null default '{}'::jsonb,
    latency_ms integer,
    provider text,
    model text,
    created_at timestamptz not null default now()
);

create table if not exists agent_tool_calls (
    id uuid primary key default gen_random_uuid(),
    workflow_id uuid not null references agent_workflows(id) on delete cascade,
    agent_id text,
    tool_name text not null,
    input_json jsonb not null default '{}'::jsonb,
    output_json jsonb not null default '{}'::jsonb,
    error_json jsonb not null default '{}'::jsonb,
    status text not null default 'succeeded',
    latency_ms integer,
    created_at timestamptz not null default now()
);

create table if not exists agent_llm_calls (
    id uuid primary key default gen_random_uuid(),
    workflow_id uuid not null references agent_workflows(id) on delete cascade,
    agent_id text not null,
    provider text not null,
    model text not null,
    prompt_hash text not null,
    input_summary_json jsonb not null default '{}'::jsonb,
    output_json jsonb not null default '{}'::jsonb,
    error_json jsonb not null default '{}'::jsonb,
    tokens_input integer,
    tokens_output integer,
    cost_usd numeric(12,6),
    latency_ms integer,
    status text not null default 'succeeded',
    created_at timestamptz not null default now()
);

create table if not exists human_approval_gates (
    id uuid primary key default gen_random_uuid(),
    workflow_id uuid not null references agent_workflows(id) on delete cascade,
    workspace_id uuid not null references workspaces(id) on delete restrict,
    gate_type text not null,
    status text not null default 'waiting' check (status in ('waiting', 'approved', 'rejected', 'edited')),
    requested_action_json jsonb not null default '{}'::jsonb,
    evidence_json jsonb not null default '{}'::jsonb,
    approver_user_id uuid,
    decision_note text,
    created_at timestamptz not null default now(),
    decided_at timestamptz
);

create index if not exists agent_workflows_workspace_account_import_idx on agent_workflows(workspace_id, account_import_id, created_at desc);
create index if not exists agent_workflows_workspace_upload_idx on agent_workflows(workspace_id, upload_id, created_at desc);
create index if not exists agent_workflow_checkpoints_workflow_idx on agent_workflow_checkpoints(workflow_id, created_at);
create index if not exists agent_workflow_events_workflow_idx on agent_workflow_events(workflow_id, created_at);
create index if not exists agent_workflow_events_workspace_idx on agent_workflow_events(workspace_id, created_at desc);
create index if not exists agent_tool_calls_workflow_idx on agent_tool_calls(workflow_id, created_at);
create index if not exists agent_llm_calls_workflow_idx on agent_llm_calls(workflow_id, created_at);
create index if not exists human_approval_gates_workspace_status_idx on human_approval_gates(workspace_id, status, created_at desc);

alter table agent_workflow_checkpoints enable row level security;
alter table agent_workflow_events enable row level security;
alter table agent_tool_calls enable row level security;
alter table agent_llm_calls enable row level security;
alter table human_approval_gates enable row level security;

create policy agent_workflow_checkpoints_select_workspace_members on agent_workflow_checkpoints for select using (
    exists (
        select 1 from agent_workflows
        where agent_workflows.id = agent_workflow_checkpoints.workflow_id
        and public.current_user_is_workspace_member(agent_workflows.workspace_id)
    )
);
create policy agent_workflow_checkpoints_insert_workspace_operators on agent_workflow_checkpoints for insert with check (
    exists (
        select 1 from agent_workflows
        where agent_workflows.id = agent_workflow_checkpoints.workflow_id
        and public.current_user_has_workspace_role(agent_workflows.workspace_id, array['owner', 'admin', 'analyst'])
    )
);

create policy agent_workflow_events_select_workspace_members on agent_workflow_events for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_workflow_events_insert_workspace_operators on agent_workflow_events for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy agent_tool_calls_select_workspace_members on agent_tool_calls for select using (
    exists (
        select 1 from agent_workflows
        where agent_workflows.id = agent_tool_calls.workflow_id
        and public.current_user_is_workspace_member(agent_workflows.workspace_id)
    )
);
create policy agent_tool_calls_insert_workspace_operators on agent_tool_calls for insert with check (
    exists (
        select 1 from agent_workflows
        where agent_workflows.id = agent_tool_calls.workflow_id
        and public.current_user_has_workspace_role(agent_workflows.workspace_id, array['owner', 'admin', 'analyst'])
    )
);

create policy agent_llm_calls_select_workspace_members on agent_llm_calls for select using (
    exists (
        select 1 from agent_workflows
        where agent_workflows.id = agent_llm_calls.workflow_id
        and public.current_user_is_workspace_member(agent_workflows.workspace_id)
    )
);
create policy agent_llm_calls_insert_workspace_operators on agent_llm_calls for insert with check (
    exists (
        select 1 from agent_workflows
        where agent_workflows.id = agent_llm_calls.workflow_id
        and public.current_user_has_workspace_role(agent_workflows.workspace_id, array['owner', 'admin', 'analyst'])
    )
);

create policy human_approval_gates_select_workspace_members on human_approval_gates for select using (public.current_user_is_workspace_member(workspace_id));
create policy human_approval_gates_insert_workspace_operators on human_approval_gates for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy human_approval_gates_update_workspace_approvers on human_approval_gates for update
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'approver']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'approver']));

comment on table agent_workflow_events is 'Durable agent workflow trace events. Agents create recommendations only and cannot execute live Amazon Ads changes.';
comment on table human_approval_gates is 'Approval gates for workflow recommendations. Approval decisions are audited and do not mutate live Amazon Ads.';
