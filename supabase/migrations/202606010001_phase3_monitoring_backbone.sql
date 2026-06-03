-- Phase 3 Monitoring Backbone: Daily Snapshots, Day-7 ACOS Checkpoints,
-- Campaign-Lock State Machine, and Rule Calibration Table.
--
-- Implements the closed-loop optimization infrastructure:
--   1. daily_monitoring_snapshots — time-series view of campaign/term performance
--   2. day7_acos_checkpoints — ACOS evaluation checkpoint (reads snapshots)
--   3. campaign_lock_state — state machine for campaign mutations
--   4. rule_calibration — deterministic rule thresholds with bounded adjustment
--   5. token_usage_by_workspace — per-workspace AI token/cost attribution

BEGIN;

-- ── 1. Daily Monitoring Snapshots ──────────────────────────────────────
-- Stores a daily snapshot of campaign/search-term/ad-group performance
-- so the system can replay 14/30/60-day windows for backtesting.

CREATE TABLE IF NOT EXISTS daily_monitoring_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL,
    product_id      UUID NOT NULL,
    campaign_name   TEXT NOT NULL,
    ad_group_name   TEXT NOT NULL DEFAULT '',
    targeting       TEXT NOT NULL DEFAULT '',
    customer_search_term TEXT NOT NULL DEFAULT '',
    match_type      TEXT,
    snapshot_date   DATE NOT NULL,  -- the calendar date this snapshot covers
    impressions     INTEGER NOT NULL DEFAULT 0,
    clicks          INTEGER NOT NULL DEFAULT 0,
    spend           NUMERIC(12,4) NOT NULL DEFAULT 0,
    sales           NUMERIC(12,4) NOT NULL DEFAULT 0,
    orders          INTEGER NOT NULL DEFAULT 0,
    units           INTEGER,
    cpc             NUMERIC(12,4),
    ctr             NUMERIC(9,4),
    cvr             NUMERIC(9,4),
    acos            NUMERIC(9,4),
    roas            NUMERIC(12,4),
    raw_metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_import_id UUID,  -- which MonitoringImport produced this row
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One row per workspace/product/campaign/entity per day
    UNIQUE (workspace_id, product_id, campaign_name, ad_group_name, targeting, customer_search_term, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_snaps_ws_product_date
    ON daily_monitoring_snapshots (workspace_id, product_id, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_snaps_ws_campaign
    ON daily_monitoring_snapshots (workspace_id, campaign_name, snapshot_date DESC);

-- Enable RLS
ALTER TABLE daily_monitoring_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY daily_snaps_workspace_isolation
    ON daily_monitoring_snapshots
    FOR ALL
    USING (workspace_id = current_setting('app.current_workspace_id')::uuid);


-- ── 2. Day-7 ACOS Checkpoints ─────────────────────────────────────────
-- After 7 days post-recommendation-approval, the system inserts a
-- checkpoint row comparing pre-recommendation metrics to 7-day-later metrics.

CREATE TABLE IF NOT EXISTS day7_acos_checkpoints (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL,
    product_id              UUID NOT NULL,
    recommendation_id       UUID NOT NULL,  -- the approved recommendation
    approved_at             TIMESTAMPTZ NOT NULL,
    checkpoint_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    pre_acos                NUMERIC(9,4) NOT NULL,
    pre_spend               NUMERIC(12,4) NOT NULL,
    pre_sales               NUMERIC(12,4) NOT NULL,
    pre_clicks              INTEGER NOT NULL,
    pre_orders              INTEGER NOT NULL,
    post_acos               NUMERIC(9,4),
    post_spend              NUMERIC(12,4),
    post_sales              NUMERIC(12,4),
    post_clicks             INTEGER,
    post_orders             INTEGER,
    acos_delta_pct          NUMERIC(9,4),  -- (post - pre) / pre * 100
    sales_delta_pct         NUMERIC(9,4),
    outcome                 TEXT,  -- improved | worsened | unchanged | insufficient_data
    snapshot_days_used      INTEGER NOT NULL DEFAULT 7,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One checkpoint per recommendation
    UNIQUE (recommendation_id)
);

CREATE INDEX IF NOT EXISTS idx_day7_checkpoints_ws_product
    ON day7_acos_checkpoints (workspace_id, product_id);
CREATE INDEX IF NOT EXISTS idx_day7_checkpoints_outcome
    ON day7_acos_checkpoints (outcome)
    WHERE outcome IS NOT NULL;

ALTER TABLE day7_acos_checkpoints ENABLE ROW LEVEL SECURITY;

CREATE POLICY day7_checkpoints_workspace_isolation
    ON day7_acos_checkpoints
    FOR ALL
    USING (workspace_id = current_setting('app.current_workspace_id')::uuid);


-- ── 3. Campaign-Lock State Machine ─────────────────────────────────────
-- Tracks which campaigns/entities are in a locked state (changes paused
-- pending review, cooldown period, etc.). Phase 3 requires this to
-- prevent rapid-fire changes before the 14-day monitoring window closes.

CREATE TABLE IF NOT EXISTS campaign_lock_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL,
    product_id      UUID NOT NULL,
    campaign_name   TEXT NOT NULL,
    entity_type     TEXT NOT NULL,  -- campaign | ad_group | target | search_term
    entity_key      TEXT NOT NULL,  -- normalized key for dedup
    lock_type       TEXT NOT NULL,  -- manual | auto_cooldown | pending_review | strategy | budget_gate
    locked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until    TIMESTAMPTZ,    -- NULL = indefinite
    locked_by       TEXT,           -- user_id or 'system'
    reason          TEXT,
    recommendation_id UUID,        -- the recommendation that triggered the lock
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_lock_ws
    ON campaign_lock_state (workspace_id, product_id, campaign_name);
CREATE INDEX IF NOT EXISTS idx_campaign_lock_time
    ON campaign_lock_state (locked_until)
    WHERE locked_until IS NOT NULL;

ALTER TABLE campaign_lock_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY campaign_lock_workspace_isolation
    ON campaign_lock_state
    FOR ALL
    USING (workspace_id = current_setting('app.current_workspace_id')::uuid);


-- ── 4. Rule Calibration Table ──────────────────────────────────────────
-- Stores bounded adjustments to deterministic rule thresholds based on
-- learning feedback outcomes. The nightly job reads this table and applies
-- adjustments within ±20% bounds.

CREATE TABLE IF NOT EXISTS rule_calibration (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID NOT NULL,
    product_id          UUID,
    rule_name           TEXT NOT NULL,
    parameter           TEXT NOT NULL,  -- e.g. "min_clicks_for_negative", "max_bid_increase_pct"
    original_value      NUMERIC(12,4) NOT NULL,
    current_value       NUMERIC(12,4) NOT NULL,
    adjustment_pct      NUMERIC(9,4) NOT NULL DEFAULT 0,  -- e.g. -10.0 means 10% reduction
    bounded_min         NUMERIC(12,4) NOT NULL,  -- hard floor (±20% of original)
    bounded_max         NUMERIC(12,4) NOT NULL,  -- hard ceiling (±20% of original)
    feedback_cycle      INTEGER NOT NULL DEFAULT 1,  -- which analysis cycle produced this
    outcome_evidence    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- counts, accuracy, etc.
    last_adjusted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rule_calibration_ws_rule
    ON rule_calibration (workspace_id, rule_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_calibration_unique
    ON rule_calibration (workspace_id, COALESCE(product_id, '00000000-0000-0000-0000-000000000000'::uuid), rule_name, parameter);

ALTER TABLE rule_calibration ENABLE ROW LEVEL SECURITY;

CREATE POLICY rule_calibration_workspace_isolation
    ON rule_calibration
    FOR ALL
    USING (workspace_id = current_setting('app.current_workspace_id')::uuid);


-- ── 5. Support for workspace_id in ai_runs (if not present) ────────────
-- The token_usage view references workspace_id on ai_runs.
-- Ensure it exists before creating the view.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_runs' AND column_name = 'workspace_id'
    ) THEN
        ALTER TABLE ai_runs ADD COLUMN workspace_id UUID;
        CREATE INDEX IF NOT EXISTS idx_ai_runs_workspace ON ai_runs (workspace_id);
    END IF;
END $$;


-- ── 6. Token Usage by Workspace View ───────────────────────────────────
-- Aggregates ai_runs table to produce per-workspace token/cost attribution.
-- This public view uses SECURITY INVOKER so ai_runs RLS remains effective.

CREATE OR REPLACE VIEW token_usage_by_workspace
WITH (security_invoker = true) AS
SELECT
    workspace_id,
    provider,
    model,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded_calls,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_calls,
    SUM(latency_ms) AS total_latency_ms,
    AVG(latency_ms)::INTEGER AS avg_latency_ms,
    -- Extract token counts from output_json if present (provider-dependent)
    SUM(COALESCE((output_json->'usage'->>'total_tokens')::INTEGER, 0)) AS estimated_total_tokens,
    SUM(COALESCE((output_json->'usage'->>'prompt_tokens')::INTEGER, 0)) AS estimated_prompt_tokens,
    SUM(COALESCE((output_json->'usage'->>'completion_tokens')::INTEGER, 0)) AS estimated_completion_tokens,
    MIN(created_at) AS first_call_at,
    MAX(created_at) AS last_call_at
FROM ai_runs
GROUP BY workspace_id, provider, model
ORDER BY workspace_id, total_calls DESC;

COMMENT ON VIEW token_usage_by_workspace IS
    'Per-workspace AI token and cost attribution view. Sources from ai_runs table. '
    'Token counts are estimates based on provider response metadata. '
    'SECURITY INVOKER ensures ai_runs RLS applies for API callers.';


COMMIT;
