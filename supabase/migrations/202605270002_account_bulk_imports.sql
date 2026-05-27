alter type upload_source_type add value if not exists 'single_product_report';
alter type upload_source_type add value if not exists 'account_bulk_report';
alter type upload_source_type add value if not exists 'sponsored_products_search_term_report';
alter type upload_source_type add value if not exists 'sponsored_products_targeting_report';
alter type upload_source_type add value if not exists 'sponsored_products_campaign_report';
alter type upload_source_type add value if not exists 'bulk_sheet';
alter type upload_source_type add value if not exists 'unknown_report';

alter table uploads alter column product_id drop not null;
alter table upload_parse_runs alter column product_id drop not null;
alter table upload_parsed_rows alter column product_id drop not null;
alter table upload_parse_errors alter column product_id drop not null;

alter table uploads add constraint uploads_workspace_id_id_key unique (workspace_id, id);
alter table upload_parse_runs add constraint upload_parse_runs_workspace_id_id_key unique (workspace_id, id);

create table if not exists account_imports (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    upload_id uuid not null,
    parse_run_id uuid not null,
    report_type text not null,
    status text not null default 'detected' check (status in ('detected', 'needs_mapping', 'ready_for_analysis', 'processing', 'succeeded', 'failed')),
    detected_report_type text not null check (detected_report_type in (
        'single_product_report',
        'account_bulk_report',
        'sponsored_products_search_term_report',
        'sponsored_products_targeting_report',
        'sponsored_products_campaign_report',
        'bulk_sheet',
        'unknown_report'
    )),
    detection_confidence text not null check (detection_confidence in ('high', 'medium', 'low')),
    total_rows integer not null default 0 check (total_rows >= 0),
    processed_rows integer not null default 0 check (processed_rows >= 0),
    error_rows integer not null default 0 check (error_rows >= 0),
    data_quality_warnings_json jsonb not null default '[]'::jsonb,
    created_by uuid,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint account_imports_upload_fk
        foreign key (workspace_id, upload_id)
        references uploads(workspace_id, id)
        on delete restrict,
    constraint account_imports_parse_run_fk
        foreign key (workspace_id, parse_run_id)
        references upload_parse_runs(workspace_id, id)
        on delete restrict
);

create table if not exists account_import_entities (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    account_import_id uuid not null references account_imports(id) on delete restrict,
    product_id uuid,
    asin text,
    sku text,
    product_name text,
    campaign_name text,
    ad_group_name text,
    targeting text,
    customer_search_term text,
    entity_type text not null check (entity_type in ('account', 'product', 'campaign', 'ad_group', 'target', 'search_term')),
    entity_key text not null,
    resolution_status text not null check (resolution_status in ('matched_existing_product', 'suggested_new_product', 'unknown_product', 'needs_user_mapping')),
    metrics_json jsonb not null default '{}'::jsonb,
    raw_row_refs_json jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    constraint account_import_entities_product_fk
        foreign key (product_id, workspace_id)
        references product_profiles(id, workspace_id)
        on delete restrict
);

create table if not exists product_mapping_suggestions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    account_import_id uuid not null references account_imports(id) on delete restrict,
    asin text,
    sku text,
    detected_product_name text,
    suggested_product_id uuid,
    status text not null default 'pending' check (status in ('pending', 'accepted', 'rejected', 'manually_mapped')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint product_mapping_suggestions_product_fk
        foreign key (suggested_product_id, workspace_id)
        references product_profiles(id, workspace_id)
        on delete restrict
);

alter table recommendations
    alter column product_id drop not null,
    alter column monitoring_import_id drop not null,
    alter column snapshot_id drop not null,
    add column if not exists account_import_id uuid references account_imports(id) on delete restrict,
    add column if not exists entity_key text,
    add column if not exists decision_source text,
    add column if not exists agent_run_id uuid references ai_runs(id) on delete set null,
    add column if not exists ai_run_id uuid references ai_runs(id) on delete set null,
    add column if not exists approval_boundary jsonb not null default '{"requires_human_approval": true, "executes_live_amazon_change": false}'::jsonb;

alter table agent_configs
    add column if not exists provider text not null default 'deepseek',
    add column if not exists model text,
    add column if not exists max_rows_per_ai_call integer not null default 500 check (max_rows_per_ai_call > 0),
    add column if not exists max_products_per_run integer not null default 50 check (max_products_per_run > 0),
    add column if not exists max_groups_per_ai_call integer not null default 100 check (max_groups_per_ai_call > 0),
    add column if not exists analysis_depth text not null default 'standard' check (analysis_depth in ('quick', 'standard', 'deep')),
    add column if not exists include_account_level_analysis boolean not null default true,
    add column if not exists include_product_level_analysis boolean not null default true,
    add column if not exists include_campaign_level_analysis boolean not null default true,
    add column if not exists include_keyword_level_analysis boolean not null default true,
    add column if not exists include_search_term_level_analysis boolean not null default true,
    add column if not exists allow_keep_running boolean not null default true,
    add column if not exists allow_increase_bid boolean not null default true,
    add column if not exists allow_decrease_bid boolean not null default true,
    add column if not exists allow_pause_review boolean not null default true,
    add column if not exists allow_negative_exact boolean not null default true,
    add column if not exists allow_negative_phrase boolean not null default true,
    add column if not exists allow_move_to_exact boolean not null default true,
    add column if not exists allow_budget_review boolean not null default true,
    add column if not exists allow_data_quality_review boolean not null default true,
    add column if not exists allow_product_mapping_recommendations boolean not null default true,
    add column if not exists max_bid_increase_multiplier numeric(6,4) not null default 1.1000,
    add column if not exists max_bid_decrease_multiplier numeric(6,4) not null default 0.9000,
    add column if not exists require_high_confidence_for_pause boolean not null default true,
    add column if not exists require_high_confidence_for_negative_keywords boolean not null default true,
    add column if not exists require_min_clicks_before_action integer not null default 10,
    add column if not exists require_min_spend_before_action numeric(12,4) not null default 10.0000,
    add column if not exists target_acos_override numeric(8,4),
    add column if not exists min_orders_for_scaling integer not null default 2,
    add column if not exists min_roas_for_scaling numeric(8,4) not null default 2.0000,
    add column if not exists custom_system_instruction text,
    add column if not exists custom_business_goal text,
    add column if not exists optimization_goal text not null default 'conservative_profitability',
    add column if not exists brand_safety_notes text,
    add column if not exists competitor_notes text,
    add column if not exists product_margin_notes text,
    add column if not exists recommendation_language text not null default 'en',
    add column if not exists explanation_detail text not null default 'normal' check (explanation_detail in ('simple', 'normal', 'expert')),
    add column if not exists show_raw_ai_reasoning_summary boolean not null default false,
    add column if not exists show_metric_evidence boolean not null default true,
    add column if not exists require_action_risk_note boolean not null default true,
    add column if not exists chunk_strategy text not null default 'by_product' check (chunk_strategy in ('by_product', 'by_campaign', 'by_entity_priority'));

create index if not exists account_imports_workspace_idx on account_imports(workspace_id, created_at desc);
create index if not exists account_imports_upload_idx on account_imports(workspace_id, upload_id);
create index if not exists account_import_entities_import_idx on account_import_entities(workspace_id, account_import_id, entity_type);
create index if not exists account_import_entities_product_idx on account_import_entities(workspace_id, product_id);
create index if not exists account_import_entities_campaign_idx on account_import_entities(workspace_id, campaign_name);
create index if not exists product_mapping_suggestions_import_idx on product_mapping_suggestions(workspace_id, account_import_id, status);
create index if not exists recommendations_account_import_idx on recommendations(workspace_id, account_import_id, entity_type);

alter table account_imports enable row level security;
alter table account_import_entities enable row level security;
alter table product_mapping_suggestions enable row level security;

create policy account_imports_select_workspace_members on account_imports for select
using (public.current_user_is_workspace_member(workspace_id));
create policy account_imports_write_workspace_operators on account_imports for all
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy account_import_entities_select_workspace_members on account_import_entities for select
using (public.current_user_is_workspace_member(workspace_id));
create policy account_import_entities_write_workspace_operators on account_import_entities for all
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

create policy product_mapping_suggestions_select_workspace_members on product_mapping_suggestions for select
using (public.current_user_is_workspace_member(workspace_id));
create policy product_mapping_suggestions_write_workspace_operators on product_mapping_suggestions for all
using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));

comment on table account_imports is 'Account-level Amazon Ads report or bulk sheet imports. Analysis and recommendations remain approval-gated and do not mutate live Amazon Ads.';
comment on table account_import_entities is 'Deterministic grouping of account import rows by product, campaign, ad group, target, and search term.';
comment on table product_mapping_suggestions is 'Pending product mapping suggestions generated from uploaded ASIN, SKU, or product-name evidence. Suggestions require user confirmation.';
