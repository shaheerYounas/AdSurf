alter type recommendation_type add value if not exists 'keep_running';
alter type recommendation_type add value if not exists 'add_negative_exact';
alter type recommendation_type add value if not exists 'add_negative_phrase';
alter type recommendation_type add value if not exists 'move_to_exact';
alter type recommendation_type add value if not exists 'data_quality_review';
alter type recommendation_type add value if not exists 'budget_review';
alter type recommendation_priority add value if not exists 'critical';
alter type recommendation_status add value if not exists 'pending';

alter table recommendations
    add column if not exists entity_type text not null default 'search_term',
    add column if not exists confidence text not null default 'medium',
    add column if not exists current_metric_snapshot_json jsonb not null default '{}'::jsonb,
    add column if not exists evidence_json jsonb not null default '{}'::jsonb;

alter table ai_runs
    add column if not exists product_id uuid;

comment on column recommendations.evidence_json is
    'Deterministic monitoring evidence including rule version, thresholds, search-term metrics, and campaign/ad group/target rollups. No AI final decisions or Amazon Ads mutations are stored here.';

comment on column recommendations.entity_type is
    'Recommendation entity grain: campaign, ad_group, target, or search_term.';

comment on column recommendations.confidence is
    'Deterministic rule confidence: low, medium, or high.';
