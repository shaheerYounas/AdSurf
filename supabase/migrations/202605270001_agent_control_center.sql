create table if not exists agent_definitions (
    agent_id text primary key,
    display_name text not null,
    description text not null,
    task_type text not null,
    enabled_by_default boolean not null default true,
    allowed_actions jsonb not null default '[]'::jsonb,
    input_dependencies jsonb not null default '[]'::jsonb,
    output_type text not null,
    can_be_disabled boolean not null default true,
    can_be_rerun boolean not null default true,
    can_be_stopped boolean not null default true,
    requires_human_approval boolean not null default true,
    can_mutate_live_amazon_ads boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists agent_configs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid,
    agent_id text not null,
    enabled boolean not null default true,
    mode text not null default 'hybrid' check (mode in ('deterministic', 'ai', 'hybrid')),
    strictness_level text not null default 'balanced' check (strictness_level in ('conservative', 'balanced', 'aggressive')),
    confidence_threshold text not null default 'medium' check (confidence_threshold in ('low', 'medium', 'high')),
    max_recommendations integer not null default 100 check (max_recommendations > 0 and max_recommendations <= 1000),
    allow_bid_recommendations boolean not null default true,
    allow_negative_keyword_recommendations boolean not null default true,
    allow_pause_recommendations boolean not null default true,
    allow_budget_recommendations boolean not null default true,
    created_by uuid,
    updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists agent_workflows (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    product_id uuid,
    monitoring_import_id uuid references monitoring_imports(id) on delete restrict,
    status text not null default 'pending',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists agent_workflow_edges (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    workflow_id uuid references agent_workflows(id) on delete cascade,
    monitoring_import_id uuid references monitoring_imports(id) on delete restrict,
    source_agent_id text not null,
    target_agent_id text not null,
    status text not null default 'waiting_for_dependency',
    data_passed_summary jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists agent_run_events (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id text not null,
    agent_run_id uuid references ai_runs(id) on delete set null,
    monitoring_import_id uuid references monitoring_imports(id) on delete set null,
    event_type text not null,
    message text not null,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists agent_control_actions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id text not null,
    agent_run_id uuid references ai_runs(id) on delete set null,
    monitoring_import_id uuid references monitoring_imports(id) on delete set null,
    action text not null,
    actor_user_id uuid,
    reason text not null,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table ai_runs
    add column if not exists agent_id text,
    add column if not exists monitoring_import_id uuid,
    add column if not exists started_at timestamptz,
    add column if not exists completed_at timestamptz,
    add column if not exists stopped_at timestamptz,
    add column if not exists paused_at timestamptz,
    add column if not exists controlled_by uuid,
    add column if not exists control_reason text,
    add column if not exists input_json jsonb not null default '{}'::jsonb,
    add column if not exists error_json jsonb not null default '{}'::jsonb,
    add column if not exists dependency_agent_run_ids jsonb not null default '[]'::jsonb,
    add column if not exists recommendation_ids jsonb not null default '[]'::jsonb,
    add column if not exists mode text,
    add column if not exists strictness_level text,
    add column if not exists confidence_threshold text;

create index if not exists agent_configs_workspace_idx on agent_configs(workspace_id, product_id, agent_id);
create unique index if not exists agent_configs_scope_unique_idx on agent_configs(workspace_id, coalesce(product_id, '00000000-0000-0000-0000-000000000000'::uuid), agent_id);
create index if not exists agent_run_events_workspace_import_idx on agent_run_events(workspace_id, monitoring_import_id, created_at);
create index if not exists agent_run_events_run_idx on agent_run_events(agent_run_id, created_at);
create index if not exists agent_control_actions_workspace_idx on agent_control_actions(workspace_id, agent_id, created_at desc);
create index if not exists ai_runs_monitoring_import_idx on ai_runs(workspace_id, monitoring_import_id, created_at desc);

alter table agent_definitions enable row level security;
alter table agent_configs enable row level security;
alter table agent_workflows enable row level security;
alter table agent_workflow_edges enable row level security;
alter table agent_run_events enable row level security;
alter table agent_control_actions enable row level security;

create policy agent_definitions_select_all on agent_definitions for select using (true);
create policy agent_configs_select_workspace_members on agent_configs for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_configs_write_workspace_admins on agent_configs for all
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin']));
create policy agent_workflows_select_workspace_members on agent_workflows for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_workflows_write_workspace_operators on agent_workflows for all
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_workflow_edges_select_workspace_members on agent_workflow_edges for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_workflow_edges_write_workspace_operators on agent_workflow_edges for all
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_run_events_select_workspace_members on agent_run_events for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_run_events_insert_workspace_operators on agent_run_events for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_control_actions_select_workspace_members on agent_control_actions for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_control_actions_insert_workspace_operators on agent_control_actions for insert
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

comment on table agent_configs is 'Workspace/product-level agent controls. Agents cannot mutate live Amazon Ads and cannot bypass human approval.';
comment on table agent_control_actions is 'Audited user controls for pausing, stopping, resuming, rerunning, and configuring agents.';
comment on table agent_run_events is 'Chronological agent event timeline for Agent Control Center.';

insert into agent_definitions (
    agent_id, display_name, description, task_type, enabled_by_default, allowed_actions,
    input_dependencies, output_type, can_be_disabled, can_be_rerun, can_be_stopped,
    requires_human_approval, can_mutate_live_amazon_ads
)
values
    ('performance_import_agent', 'Performance Import Agent', 'Validates report quality, missing columns, row count, and data-quality warnings.', 'validation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '[]'::jsonb, 'report_quality_summary', true, true, true, true, false),
    ('metrics_analysis_agent', 'Metrics Analysis Agent', 'Analyzes uploaded Amazon Ads performance metrics and finds winners, wasters, and risks.', 'analysis', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["performance_import_agent"]'::jsonb, 'performance_summary', true, true, true, true, false),
    ('ai_recommendation_brain_agent', 'AI Recommendation Brain', 'Uses DeepSeek or configured fallback mode to generate recommendation decisions from normalized report evidence.', 'decision', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["metrics_analysis_agent"]'::jsonb, 'recommendation_json', true, true, true, true, false),
    ('bid_optimization_agent', 'Bid Optimization Agent', 'Reviews bid-related recommendations and explains increase, decrease, watch-lock, and bid risk logic.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'bid_recommendation_explanations', true, true, true, true, false),
    ('negative_keyword_agent', 'Negative Keyword Agent', 'Reviews wasted search terms and explains negative exact or phrase evidence.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'negative_keyword_explanations', true, true, true, true, false),
    ('pause_review_agent', 'Pause Review Agent', 'Reviews campaigns, ad groups, targets, or search terms that may need pause review.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'pause_review_explanations', true, true, true, true, false),
    ('stakeholder_reporting_agent', 'Stakeholder Reporting Agent', 'Creates dashboard summaries, executive summary, next-best actions, and approver notes.', 'reporting', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["bid_optimization_agent","negative_keyword_agent","pause_review_agent"]'::jsonb, 'dashboard_summary', true, true, true, true, false)
on conflict (agent_id) do update set
    display_name = excluded.display_name,
    description = excluded.description,
    task_type = excluded.task_type,
    enabled_by_default = excluded.enabled_by_default,
    allowed_actions = excluded.allowed_actions,
    input_dependencies = excluded.input_dependencies,
    output_type = excluded.output_type,
    can_be_disabled = excluded.can_be_disabled,
    can_be_rerun = excluded.can_be_rerun,
    can_be_stopped = excluded.can_be_stopped,
    requires_human_approval = excluded.requires_human_approval,
    can_mutate_live_amazon_ads = excluded.can_mutate_live_amazon_ads,
    updated_at = now();
