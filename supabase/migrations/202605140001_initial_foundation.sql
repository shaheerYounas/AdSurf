create extension if not exists pgcrypto;

create type workspace_role as enum ('owner', 'admin', 'analyst', 'approver', 'viewer');
create type workspace_status as enum ('active', 'archived');
create type workspace_member_status as enum ('active', 'invited', 'disabled');
create type product_profile_status as enum ('active', 'archived');
create type job_status as enum ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled');
create type outbox_status as enum ('pending', 'published', 'failed');

create table workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null default 'seller',
  status workspace_status not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table workspace_members (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete restrict,
  user_id uuid not null,
  role workspace_role not null,
  status workspace_member_status not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, user_id)
);

create table product_profiles (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete restrict,
  product_name text not null,
  asin text null check (asin is null or asin ~ '^[A-Z0-9]{10}$'),
  sku text null,
  marketplace text not null default 'US',
  currency char(3) not null default 'USD',
  target_acos numeric(8,4) not null default 0.5000 check (target_acos > 0 and target_acos <= 1),
  default_budget numeric(12,4) not null default 10.0000 check (default_budget > 0),
  default_bid numeric(12,4) not null default 1.0000 check (default_bid > 0),
  status product_profile_status not null default 'active',
  created_by uuid null,
  updated_by uuid null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table audit_logs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete restrict,
  actor_user_id uuid null,
  event_type text not null,
  object_type text not null,
  object_id uuid null,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table rule_versions (
  id uuid primary key default gen_random_uuid(),
  rule_set text not null,
  version text not null,
  description text not null default '',
  config_json jsonb not null default '{}'::jsonb,
  active_from timestamptz not null default now(),
  active_to timestamptz null,
  created_at timestamptz not null default now(),
  unique (rule_set, version)
);

create table job_queue (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete restrict,
  job_type text not null,
  status job_status not null default 'queued',
  payload_json jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  attempts integer not null default 0 check (attempts >= 0),
  locked_at timestamptz null,
  locked_by text null,
  heartbeat_at timestamptz null,
  last_error text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, job_type, idempotency_key)
);

create table outbox_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete restrict,
  event_type text not null,
  aggregate_type text not null,
  aggregate_id uuid not null,
  payload_json jsonb not null default '{}'::jsonb,
  status outbox_status not null default 'pending',
  published_at timestamptz null,
  created_at timestamptz not null default now()
);

create index idx_workspace_members_workspace_id on workspace_members(workspace_id);
create index idx_workspace_members_user_id on workspace_members(user_id);
create index idx_product_profiles_workspace_id on product_profiles(workspace_id);
create index idx_product_profiles_status on product_profiles(status);
create index idx_audit_logs_workspace_id_created_at on audit_logs(workspace_id, created_at desc);
create index idx_rule_versions_rule_set on rule_versions(rule_set);
create index idx_job_queue_status_locked_at on job_queue(status, locked_at);
create index idx_job_queue_workspace_id on job_queue(workspace_id);
create index idx_outbox_events_status_created_at on outbox_events(status, created_at);

