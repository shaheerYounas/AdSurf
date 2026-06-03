# Amazon Ads Implementation Plan

## Safety Rule
No campaign creation, bid change, or negative keyword action can be applied without validation, explanation, risk label, and approval.

The MVP must remain approval-first and bulk-sheet-first. The system may validate, normalize, explain, recommend, preview, and export approved changes. It must not silently mutate Amazon Ads. Any future live Amazon Ads API action requires an explicit approval record, actor identity, audit log, and a separate execution boundary.

## Backend Architecture
The backend should remain modular FastAPI services with deterministic rules as the default path and AI as an explanation or reasoning layer only.

Recommended service boundaries:
- `FileUploadService`: Creates workspace-scoped upload records, validates metadata, stores raw files, and queues parsing.
- `ReportParserService`: Parses CSV/XLS/XLSX safely without executing formulas or trusting spreadsheet instructions.
- `ReportValidationService`: Detects report type, required columns, hidden header issues, marketplace/currency/date mismatches, duplicate rows, and unsafe data.
- `MetricCalculatorService`: Normalizes numeric metrics and recalculates CTR, CPC, CVR, ACOS, and ROAS.
- `SearchTermClassifierService`: Classifies terms as keyword, ASIN/product target, branded, competitor, generic, irrelevant, low-data, or duplicate.
- `RecommendationService`: Generates approval-required recommendations from normalized evidence.
- `RiskPolicyValidatorService`: Blocks unsafe actions and attaches risk labels and blocked reasons.
- `CampaignPlanService`: Builds campaign plan drafts from approved recommendations or approved keyword sets.
- `NegativeKeywordService`: Previews negative exact/phrase candidates before approval/export.
- `BulkExportService`: Generates Amazon bulk sheet exports only after approval.
- `MonitoringService`: Imports later performance reports and evaluates outcomes.
- `AuditLogService`: Records every customer-impacting decision and workflow transition.

All decision-making services should support deterministic rules and AI-powered reasoning through the `DualPathDecisionService[T]` pattern, with deterministic fallback.

## Database Tables
Existing core tables should be used where possible:
- `workspaces`, `workspace_members`
- `product_profiles`
- `uploads`
- `upload_parse_runs`, `upload_parsed_rows`, `upload_parse_errors`
- `account_imports`, `account_import_entities`, `product_mapping_suggestions`
- `monitoring_imports`, `monitoring_snapshots`
- `recommendations`, `recommendation_decisions`
- `campaign_plans`, `bulk_exports`
- `approvals`, `audit_logs`
- `ai_runs`, `rule_versions`, `job_queue`, `outbox_events`
- workflow tables for durable agent/workflow state and human approval gates

Likely additions or refinements:
- `report_validation_runs`: validation score, blocking errors, warnings, report type, marketplace, currency, date range, and source upload.
- `normalized_report_rows`: optional canonical row store if normalized metrics need to be queried separately from raw parsed JSON.
- `search_term_classifications`: classification, reasons, confidence, source row refs, and classifier version.
- `negative_keyword_previews`: candidate negative actions grouped by campaign/ad group/search term with risk labels.
- `budget_confirmations`: total daily exposure, approver, note, and confirmation timestamp.
- `recommendation_exports`: links approved recommendations to generated bulk export rows if export-from-recommendations is separated from campaign-plan exports.

Every workspace-owned table must include `workspace_id`, enforce workspace isolation, and be covered by RLS and API role checks.

## API Endpoints
Existing endpoints cover much of the foundation. The professional workflow should expose a clearer Sponsored Products Search Term Report path:

- `POST /v1/workspaces/{workspace_id}/products/{product_id}/sp-search-term-workflows`
  Creates a guided workflow from a processed upload.
- `GET /v1/workspaces/{workspace_id}/sp-search-term-workflows/{workflow_id}`
  Returns step state: upload, validation, normalization, analysis, recommendations, campaign builder, negatives, budget, export, monitoring.
- `POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/validate-report`
  Runs or returns deterministic validation.
- `POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/normalize-metrics`
  Creates normalized metric rows after validation passes or records blocked reasons.
- `POST /v1/workspaces/{workspace_id}/normalized-imports/{import_id}/classify-search-terms`
  Classifies search terms.
- `POST /v1/workspaces/{workspace_id}/normalized-imports/{import_id}/recommendations`
  Generates recommendation records with approval boundaries.
- `GET /v1/workspaces/{workspace_id}/recommendations`
  Lists approval queue.
- `POST /v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/approve`
  Records approval only.
- `POST /v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/reject`
  Records rejection only.
- `GET /v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/why`
  Returns explanation, evidence, risk labels, and blocked reasons.
- `POST /v1/workspaces/{workspace_id}/recommendation-sets/{set_id}/negative-keyword-preview`
  Builds negative exact/phrase preview.
- `POST /v1/workspaces/{workspace_id}/recommendation-sets/{set_id}/campaign-plan`
  Creates campaign plan draft.
- `POST /v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/confirm-budget`
  Records budget confirmation.
- `POST /v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/exports`
  Generates bulk sheet only after plan approval and budget confirmation.
- `POST /v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports`
  Imports new performance reports for monitoring.

## File Upload Validation Pipeline
Validation should run before any analysis or recommendation generation:

1. Validate extension, MIME type, file size, and storage path.
2. Parse CSV/XLS/XLSX safely.
3. Normalize headers by trimming hidden spaces and mapping known Amazon aliases.
4. Detect report type and confidence.
5. Verify required Sponsored Products Search Term Report columns.
6. Validate date range and detect mixed date windows.
7. Validate marketplace and currency against product/workspace expectations.
8. Validate numeric metric columns.
9. Validate percentage columns as either decimal ratios or percent strings.
10. Handle blank ACOS safely.
11. Detect duplicate rows and duplicate search-term contexts.
12. Separate ASIN/product-target search terms from keyword text.
13. Decide whether data is sufficient for optimization or only safe for review.

Validation output must include blocking errors, warnings, risk labels, evidence, and next allowed step.

## Metric Calculation Engine
The metric engine must recalculate:
- CTR = clicks / impressions
- CPC = spend / clicks
- CVR = orders / clicks
- ACOS = spend / sales
- ROAS = sales / spend

Divide-by-zero rules:
- If impressions = 0, CTR is `null`.
- If clicks = 0, CPC and CVR are `null`.
- If sales = 0, ACOS is `null`, never `0`.
- If spend > 0 and sales = 0, label the row `Spend with No Sales`.
- If spend = 0, ROAS is `null`.

The engine should compare uploaded Amazon metrics to recalculated metrics and flag mismatches beyond a defined tolerance.

## Recommendation Engine
Recommendations must be deterministic-rule backed first, with AI only as bounded reasoning/explanation unless explicitly configured for hybrid mode.

Every recommendation must include:
- action type
- search term or target
- product/campaign/ad group context
- normalized metrics
- reason list
- rule version
- risk level
- confidence level
- blocked reason if unsafe
- `requires_human_approval: true`
- `executes_live_amazon_change: false`

Unsafe recommendations should be saved as blocked or data-quality review items, not silently dropped.

## Campaign Builder Flow
Campaign builder must be review-first:

1. User selects approved recommendations or approved keyword set.
2. System separates keyword campaigns from ASIN/product-targeting campaigns.
3. System groups terms by intent, match type, and risk.
4. System creates draft campaign structure.
5. System attaches naming, budgets, bids, negative structure, and safety summary.
6. User reviews campaign draft and warnings.
7. User confirms total possible daily budget.
8. User approves the plan with a note.
9. System can generate a bulk sheet export.

Campaign builder must not create live campaigns in MVP.

## Negative Keyword Preview Flow
Negative keyword preview should be its own approval-focused step:

1. Collect negative exact and negative phrase candidates.
2. Exclude converting terms unless explicitly marked as blocked review.
3. Show campaign/ad group placement level.
4. Show match type, search term, clicks, spend, orders, sales, ACOS, and reason.
5. Show risk of overblocking.
6. Group duplicates and conflicts.
7. Require human approval before including negatives in export.

ASIN/product-targeting rows must not be treated as normal keyword negatives without explicit product-targeting review.

## Monitoring Scheduler
Monitoring should evaluate approved/exported actions after new performance reports are imported.

MVP scheduler behavior:
- Use job queue records for local/manual processing.
- Run monitoring import normalization.
- Compare new performance against prior recommendations and approved actions.
- Evaluate 7-day and 14-day checkpoints where applicable.
- Generate learning feedback and new recommendations only when enough evidence exists.
- Suppress recommendations for locked/watch-only campaigns.

Production scheduler target:
- A durable worker or scheduled job processes queued monitoring jobs.
- Job retries are idempotent.
- Failures write safe, user-visible errors.
- No scheduler job executes live Amazon Ads mutations.

## Audit Logging
Audit logs must record:
- upload received
- parse started/completed/failed
- validation run and validation result
- normalization run
- recommendation generation
- blocked recommendation reasons
- approval and rejection decisions
- campaign plan creation
- budget confirmation
- export generation
- monitoring import and evaluation
- AI provider/model/prompt metadata when AI is used

Every audit event should include workspace, actor when available, entity type, entity id, rule version, decision source, and execution boundary.

## Frontend Screens
The frontend should expose a guided workflow, not a single hidden "Optimize" button.

Screens:
- Upload Report
- Validation Results
- Normalized Metrics
- Search Term Analysis
- Recommendation Queue
- Recommendation Why Drawer
- Campaign Builder
- Negative Keyword Preview
- Budget Confirmation
- Bulk Export Review/Download
- Monitoring Dashboard
- Audit Log

Each screen needs loading, error, empty, and success states. Warnings must be shown before campaign creation, negative keyword export, and budget confirmation.

## Testing Plan
Backend unit tests:
- missing columns
- hidden spaces in columns
- report type mismatch
- wrong marketplace
- wrong currency
- invalid date range
- duplicate rows
- numeric parsing failures
- percentage parsing as `0.25` and `25%`
- blank ACOS
- zero sales
- zero clicks
- ASIN search terms
- low-data terms
- metric recalculation mismatches
- recommendation blocked reasons
- negative keyword safety
- budget confirmation gate

Integration tests:
- upload -> parse -> validate -> normalize
- normalize -> classify -> recommend
- recommendation approval/rejection audit
- approved recommendations -> negative preview
- approved plan -> budget confirmation -> export
- monitoring import -> recommendation generation

Frontend tests:
- guided workflow step states
- validation warning rendering
- recommendation why drawer
- approve/reject modal note requirement
- campaign builder warning display
- negative keyword preview display
- budget confirmation requirement
- export success and error states

## MVP Phases
### Phase 1: Validation And Normalization
- Harden Sponsored Products Search Term Report validation.
- Create canonical validation result shape.
- Normalize metrics and store/retrieve normalized evidence.
- Add tests for all upload and metric edge cases.

### Phase 2: Search Term Analysis And Recommendations
- Wire search term classification into recommendation generation.
- Standardize recommendation payloads with reasons, risk, confidence, blocked reason, and approval boundary.
- Add Why drawer support.

### Phase 3: Negative Keyword Preview
- Build negative exact/phrase preview.
- Add conflict and overblocking warnings.
- Require approval before export inclusion.

### Phase 4: Campaign Builder And Budget Confirmation
- Generate campaign plans from approved recommendations.
- Separate keyword vs ASIN/product-targeting plans.
- Require explicit total daily budget confirmation.

### Phase 5: Bulk Export
- Generate Amazon bulk sheet exports from approved plans and approved recommendations.
- Store export metadata and audit log.
- Keep export as the only MVP execution handoff.

### Phase 6: Monitoring And Learning
- Schedule monitoring imports.
- Compare post-export reports to approved recommendations.
- Generate learning feedback and updated recommendations.
- Add dashboard summary and audit trail.

### Phase 7: Production Hardening
- Verify Supabase RLS and auth claims.
- Move local worker behavior to durable worker/scheduler infrastructure.
- Add observability, retries, idempotency, and performance checks.
- Run full E2E workflow tests before release.
