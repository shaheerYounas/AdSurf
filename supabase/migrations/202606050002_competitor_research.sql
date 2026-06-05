-- Migration: Competitor research tables
-- Adds tables for live Amazon SERP competitor research runs,
-- per-keyword results, captured competitor products, and AI insights.

-- ─────────────────────────────────────────────
-- Enums
-- ─────────────────────────────────────────────

do $$ begin
  create type competitor_research_status as enum (
    'queued',
    'running',
    'paused_manual_verification',
    'succeeded',
    'failed',
    'cancelled'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type competitor_keyword_status as enum (
    'queued',
    'running',
    'succeeded',
    'failed',
    'skipped'
  );
exception when duplicate_object then null; end $$;

-- ─────────────────────────────────────────────
-- competitor_research_runs
-- One record per research session (may cover many keywords).
-- ─────────────────────────────────────────────

create table if not exists competitor_research_runs (
  id                          uuid primary key default gen_random_uuid(),
  workspace_id                uuid not null references workspaces(id) on delete restrict,
  product_id                  uuid null references product_profiles(id) on delete set null,

  -- Settings at time of run
  marketplace                 text not null default 'US',
  max_keywords_per_run        integer not null default 20,
  max_competitors_per_keyword integer not null default 10,
  delay_min_seconds           numeric(5,2) not null default 2.0,
  delay_max_seconds           numeric(5,2) not null default 5.0,
  open_product_detail_pages   boolean not null default false,
  headless                    boolean not null default false,

  -- Status
  status                      competitor_research_status not null default 'queued',
  keywords_total              integer not null default 0,
  keywords_completed          integer not null default 0,
  keywords_failed             integer not null default 0,
  products_captured           integer not null default 0,

  -- Pause/resume state
  current_keyword_index       integer not null default 0,
  paused_reason               text null,

  -- Timestamps
  started_at                  timestamptz null,
  completed_at                timestamptz null,
  error_message               text null,
  created_by                  uuid null,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);

create index if not exists idx_competitor_research_runs_workspace
  on competitor_research_runs(workspace_id, created_at desc);

create index if not exists idx_competitor_research_runs_product
  on competitor_research_runs(product_id, created_at desc);

create index if not exists idx_competitor_research_runs_status
  on competitor_research_runs(workspace_id, status)
  where status in ('queued', 'running', 'paused_manual_verification');

-- ─────────────────────────────────────────────
-- competitor_research_keywords
-- The keyword queue for a run. One row per keyword.
-- ─────────────────────────────────────────────

create table if not exists competitor_research_keywords (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references workspaces(id) on delete restrict,
  run_id          uuid not null references competitor_research_runs(id) on delete cascade,

  keyword         text not null,
  keyword_source  text null,  -- 'user_seed', 'search_term_report', 'high_spend', 'move_to_exact', 'manual'
  priority_rank   integer not null default 0,  -- lower = higher priority
  status          competitor_keyword_status not null default 'queued',

  -- Results summary (set after completion)
  search_url          text null,
  searched_at         timestamptz null,
  screenshot_path     text null,
  organic_count       integer null,
  sponsored_count     integer null,
  error_message       text null,

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_competitor_research_keywords_run
  on competitor_research_keywords(run_id, priority_rank, status);

-- ─────────────────────────────────────────────
-- competitor_research_results
-- Individual competitor product cards captured from SERP.
-- ─────────────────────────────────────────────

create table if not exists competitor_research_results (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspaces(id) on delete restrict,
  run_id              uuid not null references competitor_research_runs(id) on delete cascade,
  keyword_id          uuid not null references competitor_research_keywords(id) on delete cascade,

  -- Position / type
  position            integer not null,
  result_type         text not null default 'organic',  -- 'organic' | 'sponsored'

  -- Visible product data (all nullable — only what Amazon shows)
  asin                text null,
  title               text null,
  brand               text null,
  price_text          text null,   -- raw visible price string e.g. "$8.99"
  price_usd           numeric(12,2) null,  -- parsed USD value
  rating              numeric(3,1) null,
  review_count        integer null,
  has_coupon          boolean null,
  is_prime            boolean null,
  is_amazon_choice    boolean null,
  is_best_seller      boolean null,
  image_url           text null,
  product_url         text null,

  -- Product detail page enrichment (if open_product_detail_pages = true)
  detail_bullets_json   jsonb null,
  detail_variations     integer null,
  detail_aplus_present  boolean null,
  detail_image_count    integer null,

  created_at  timestamptz not null default now()
);

create index if not exists idx_competitor_results_run
  on competitor_research_results(run_id, keyword_id, position);

create index if not exists idx_competitor_results_asin
  on competitor_research_results(workspace_id, asin)
  where asin is not null;

-- ─────────────────────────────────────────────
-- competitor_ai_insights
-- AI-generated summary per keyword per run.
-- ─────────────────────────────────────────────

create table if not exists competitor_ai_insights (
  id                        uuid primary key default gen_random_uuid(),
  workspace_id              uuid not null references workspaces(id) on delete restrict,
  run_id                    uuid not null references competitor_research_runs(id) on delete cascade,
  keyword_id                uuid not null references competitor_research_keywords(id) on delete cascade,

  keyword                   text not null,

  -- Scores (0–100)
  opportunity_score         integer null check (opportunity_score between 0 and 100),
  competitor_strength_score integer null check (competitor_strength_score between 0 and 100),
  relevance_score           integer null check (relevance_score between 0 and 100),
  risk_score                integer null check (risk_score between 0 and 100),

  -- Labels
  competitor_strength       text null,   -- 'Low' | 'Medium' | 'High' | 'Very High'
  sponsored_intensity       text null,   -- 'Low' | 'Medium' | 'High'
  organic_difficulty        text null,   -- 'Low' | 'Medium' | 'High'
  product_market_fit        text null,   -- 'Poor' | 'Fair' | 'Good' | 'Excellent'

  -- Price and review ranges (text for display)
  avg_price_range           text null,   -- e.g. "$8.99–$12.99"
  avg_review_count          text null,   -- e.g. "2,000+"
  avg_price_min_usd         numeric(12,2) null,
  avg_price_max_usd         numeric(12,2) null,
  avg_review_count_number   integer null,

  -- Recommendation
  recommended_ad_strategy   text null,
  listing_improvement       text null,
  action_recommendation     text null,  -- 'increase_bid' | 'decrease_bid' | 'move_to_exact' | 'keep_running' | 'avoid' | 'watch'

  -- Full narrative
  full_summary              text null,

  -- Raw AI output
  ai_provider               text null,
  ai_model                  text null,
  ai_response_json          jsonb null,
  generated_at              timestamptz not null default now(),

  unique (keyword_id)  -- one insight per keyword per run
);

create index if not exists idx_competitor_ai_insights_run
  on competitor_ai_insights(run_id);

create index if not exists idx_competitor_ai_insights_workspace
  on competitor_ai_insights(workspace_id, generated_at desc);

comment on table competitor_research_runs is
  'Tracks a user-supervised competitor research session. '
  'The browser is visible (headless=false by default). '
  'If Amazon shows a CAPTCHA the run pauses with status=paused_manual_verification. '
  'No Amazon Ads live changes are made.';

comment on table competitor_ai_insights is
  'AI-generated competitive insight summaries per keyword. '
  'Used as supporting evidence in the recommendation engine alongside Ads metrics.';
