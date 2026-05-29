-- Phase 3: Campaign creation enhancements + 14-day monitoring system
-- Covers items 8, 10, 12, 16-20 from the compliance plan.

-- Campaign locks for Day 7 ACOS evaluation (item 20)
create type campaign_lock_status as enum ('active', 'locked');

create table campaign_locks (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    campaign_name text not null,
    status campaign_lock_status not null default 'locked',
    acos_at_lock numeric null,
    locked_at timestamptz not null default now(),
    locked_until timestamptz not null,
    unlocked_at timestamptz null,
    created_at timestamptz not null default now(),
    unique (workspace_id, campaign_name)
);

-- Daily budget consumption tracking (items 16, 17, 18)
create table daily_budget_snapshots (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    product_id uuid not null references product_profiles(id) on delete cascade,
    campaign_name text not null,
    snapshot_date date not null,
    daily_budget numeric not null default 10,
    spend numeric not null default 0,
    impressions integer not null default 0,
    clicks integer not null default 0,
    orders integer not null default 0,
    sales numeric not null default 0,
    acos numeric null,
    bid_multiplier numeric not null default 1.0,
    previous_bid numeric not null default 1.0,
    suggested_bid numeric not null default 1.0,
    created_at timestamptz not null default now(),
    unique (workspace_id, product_id, campaign_name, snapshot_date)
);

-- Day 7 ACOS evaluation checkpoints (item 19)
create table day7_checkpoints (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    product_id uuid not null references product_profiles(id) on delete cascade,
    campaign_name text not null,
    total_spend_7d numeric not null,
    total_sales_7d numeric not null,
    acos_7d numeric not null,
    decision text not null check (decision in ('locked', 'continue_monitoring')),
    locked_until timestamptz null,
    evaluated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (workspace_id, product_id, campaign_name)
);

-- Competitor profile for Amazon verification (items 5-7)
create table product_competitors (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    product_id uuid not null references product_profiles(id) on delete cascade,
    competitor_name text not null,
    competitor_asin text null,
    created_at timestamptz not null default now(),
    unique (workspace_id, product_id, competitor_name)
);

-- Verification status on cleaned rows (items 5-7)
alter table competitor_cleaned_rows
    add column verification_status text null check (verification_status in ('verified', 'unverified')),
    add column verification_result_json jsonb null,
    add column verified_at timestamptz null;

-- Batch size config on product profiles (item 12)
alter table product_profiles
    add column keyword_batch_size integer not null default 7 check (keyword_batch_size between 5 and 7);

-- Indexes
create index campaign_locks_workspace_idx on campaign_locks(workspace_id, campaign_name);
create index daily_budget_snapshots_date_idx on daily_budget_snapshots(workspace_id, product_id, snapshot_date desc);
create index day7_checkpoints_workspace_idx on day7_checkpoints(workspace_id, product_id);
create index product_competitors_product_idx on product_competitors(workspace_id, product_id);
create index competitor_cleaned_rows_verification_idx on competitor_cleaned_rows(verification_status);

-- RLS
alter table campaign_locks enable row level security;
alter table daily_budget_snapshots enable row level security;
alter table day7_checkpoints enable row level security;
alter table product_competitors enable row level security;

create policy campaign_locks_select_workspace_members on campaign_locks for select using (public.current_user_is_workspace_member(workspace_id));
create policy campaign_locks_insert_workspace_operators on campaign_locks for insert with check (public.current_user_has_workspace_role(workspace_id, array['owner','admin','analyst']));
create policy daily_budget_snapshots_select_workspace_members on daily_budget_snapshots for select using (public.current_user_is_workspace_member(workspace_id));
create policy daily_budget_snapshots_insert_workspace_operators on daily_budget_snapshots for insert with check (public.current_user_has_workspace_role(workspace_id, array['owner','admin','analyst']));
create policy day7_checkpoints_select_workspace_members on day7_checkpoints for select using (public.current_user_is_workspace_member(workspace_id));
create policy day7_checkpoints_insert_workspace_operators on day7_checkpoints for insert with check (public.current_user_has_workspace_role(workspace_id, array['owner','admin','analyst']));
create policy product_competitors_select_workspace_members on product_competitors for select using (public.current_user_is_workspace_member(workspace_id));
create policy product_competitors_insert_workspace_operators on product_competitors for insert with check (public.current_user_has_workspace_role(workspace_id, array['owner','admin','analyst']));

comment on table campaign_locks is 'Campaign freeze after Day 7 ACOS < 50% evaluation. Locked campaigns receive no optimization recommendations for 7 days.';
comment on table daily_budget_snapshots is 'Per-campaign daily spend, impressions, clicks, orders, sales, and ACOS for 14-day monitoring cycle.';
comment on table day7_checkpoints is 'Day 7 ACOS evaluation results. ACOS < 50% triggers a 7-day campaign lock.';
comment on table product_competitors is 'Competitor names/ASINs for Amazon search verification (Phase 1 step 3).';