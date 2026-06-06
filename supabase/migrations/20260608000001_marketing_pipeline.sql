-- Migration: Marketing pipeline persistence tables
-- Stores Phase 1 (competitor research runs), Phase 2 (campaign plans),
-- and Phase 3 (monitoring records) data for the marketing pipeline.

-- ─────────────────────────────────────────────
-- 1. marketing_research_runs
--    Lightweight summary of a keyword-scoring + Amazon-filter run.
--    (Distinct from competitor_research_runs which tracks live SERP scraping.)
-- ─────────────────────────────────────────────

create table if not exists marketing_research_runs (
  id                      uuid primary key default gen_random_uuid(),
  workspace_id            uuid not null references workspaces(id) on delete restrict,
  product_id              uuid null references product_profiles(id) on delete set null,
  product_name            text not null,
  status                  text not null default 'pending'
                            check (status in ('pending', 'processing', 'completed', 'failed')),
  total_input_keywords    integer not null default 0,
  filtered_by_score       integer not null default 0,
  filtered_by_amazon      integer not null default 0,
  approved_keywords_json  jsonb not null default '[]',
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create index if not exists idx_marketing_research_runs_workspace
  on marketing_research_runs(workspace_id);

alter table marketing_research_runs enable row level security;

create policy marketing_research_runs_select_for_workspace_members
  on marketing_research_runs
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));

-- ─────────────────────────────────────────────
-- 2. marketing_campaign_plans
--    Phase 2 output: hero campaign + grouped keyword batches.
-- ─────────────────────────────────────────────

create table if not exists marketing_campaign_plans (
  id                      uuid primary key default gen_random_uuid(),
  workspace_id            uuid not null references workspaces(id) on delete restrict,
  research_run_id         uuid null references marketing_research_runs(id) on delete set null,
  product_name            text not null,
  status                  text not null default 'draft'
                            check (status in ('draft', 'approved', 'exported')),
  hero_campaign_json      jsonb not null default '{}',
  grouped_campaigns_json  jsonb not null default '[]',
  total_keywords          integer not null default 0,
  batch_count             integer not null default 0,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create index if not exists idx_marketing_campaign_plans_workspace
  on marketing_campaign_plans(workspace_id);

alter table marketing_campaign_plans enable row level security;

create policy marketing_campaign_plans_select_for_workspace_members
  on marketing_campaign_plans
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));

-- ─────────────────────────────────────────────
-- 3. marketing_monitoring_records
--    Phase 3 output: per-campaign daily monitoring log (days 1–14).
-- ─────────────────────────────────────────────

create table if not exists marketing_monitoring_records (
  id                    uuid primary key default gen_random_uuid(),
  workspace_id          uuid not null references workspaces(id) on delete restrict,
  campaign_plan_id      uuid null references marketing_campaign_plans(id) on delete cascade,
  campaign_id           text not null,
  day_number            integer not null check (day_number between 1 and 14),
  daily_spend           numeric(12,4) not null default 0,
  daily_budget          numeric(12,4) not null default 10.0000,
  current_bid           numeric(12,4) not null default 1.0000,
  total_spend_to_date   numeric(12,4) not null default 0,
  total_sales_to_date   numeric(12,4) not null default 0,
  is_locked             boolean not null default false,
  action_taken          text null,
  new_bid               numeric(12,4) null,
  acos                  numeric(8,4) null,
  action_reason         text null,
  created_at            timestamptz not null default now()
);

create index if not exists idx_marketing_monitoring_records_workspace
  on marketing_monitoring_records(workspace_id);

alter table marketing_monitoring_records enable row level security;

create policy marketing_monitoring_records_select_for_workspace_members
  on marketing_monitoring_records
  for select
  to authenticated
  using (public.current_user_is_workspace_member(workspace_id));
