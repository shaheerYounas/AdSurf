# ADR 0004: Rule Engine Before Full AI Autonomy (Dual-Path Architecture)

## Status
Accepted and expanded (2026-05-31).

## Decision
Every decision-making service in AdSurf MUST support BOTH deterministic rule-based calculation AND AI-powered reasoning, following a dual-path pattern. The system selects which path to use based on per-workspace, per-product agent configuration (mode: `deterministic`, `ai`, or `hybrid`).

The dual-path pattern ensures:
- Deterministic path is ALWAYS available (never depends on external AI providers)
- AI path is optional and configurable
- Hybrid mode uses AI first, falls back to deterministic on any failure
- Pure AI mode returns empty results on failure (safety-first — no wrong answers)
- Human approval is ALWAYS required regardless of path

## Affected Services
All decision services follow the `DualPathDecisionService[T]` base class:
- Keyword Scoring (`DualPathKeywordScoring`)
- Competitor Scoring (`DualPathCompetitorScoring`)
- Campaign Generation (`DualPathCampaignGeneration`)
- Competitor Campaign Generation (`DualPathCompetitorCampaignGeneration`)
- Column Mapping (`DualPathColumnMapping`)
- Report Type Detection (`DualPathReportTypeDetection`)
- Keyword Review (`DualPathKeywordReview`)
- Monitoring Agents Explainer (`DualPathMonitoringAgentsExplain`)
- AI Recommendation Brain (already hybrid in `monitoring_worker.py`)
- Risk Validator (deterministic-only, never AI)

## Safety Invariants
1. AI may recommend, explain, and map — but never silently act
2. Human approval required before any customer-impacting action
3. No live Amazon Ads API mutation from any decision path
4. Deterministic fallback on AI failure
5. Every AI prompt includes safety guardrails
6. Every output includes `requires_human_approval: true` and `executes_live_amazon_change: false`

## Consequences
Rules must be versioned, tested, and auditable. AI outputs must be structured, validated against schemas, and checked against deterministic rule results. Every AI call is logged with provider, model, input hash, and status.
</replace_in_file>
<task_progress>
- [x] Explore codebase to identify all decision-making points
- [x] Create shared dual-path decision module
- [x] Implement dual-path in keyword_scoring.py (deterministic + AI)
- [x] Implement dual-path in competitor_scoring.py (deterministic + AI)
- [x] Implement dual-path in campaign_generation.py (deterministic + AI)
- [x] Implement dual-path in competitor_campaign_gen.py (deterministic + AI)
- [x] Implement dual-path in column_mapping.py (deterministic + AI)
- [x] Implement dual-path in report_type_detector.py (deterministic + AI)
- [x] Implement dual-path in keyword_review.py (deterministic + AI)
- [x] Implement dual-path in monitoring_agents.py (deterministic + AI)
- [x] Update orchestration nodes.py with dual-path routing
- [ ] Update web app API types and components for dual-path toggles
- [x] Update all .md docs to reflect dual-path architecture
- [ ] Verify implementation completeness
</task_progress>

