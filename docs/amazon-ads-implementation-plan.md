# Amazon Ads Implementation Plan

## Safety Rule
No campaign creation, bid change, or negative keyword action can be applied without validation, explanation, risk label, and approval.

The MVP must remain approval-first and bulk-sheet-first. The system may validate, normalize, explain, recommend, preview, and export approved changes. It must not silently mutate Amazon Ads. Any future live Amazon Ads API action requires an explicit approval record, actor identity, audit log, and a separate execution boundary.

## 1. Backend Architecture

### 1.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API Gateway (FastAPI/Express)                      │
│                  Authentication, Rate Limiting, Request Routing            │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         │                               │                               │
         ▼                               ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐         ┌─────────────────────┐
│  FileUploadService  │         │  ReportParserService│         │  ReportValidation   │
│                     │───────▶ │                     │───────▶ │      Service        │
│  - Workspace-scoped │         │   - CSV/XLS parsing │         │   - Report type     │
│  - Metadata storage │         │   - Formula-safe    │         │   - Column checks   │
│  - Queue parsing    │         │   - Data extraction │         │   - Marketplace     │
└─────────────────────┘         └─────────────────────┘         │   - Currency      │
                                                                │   - Date validation │
                                                                └─────────────────────┘
                                                                         │
                                                                         ▼
┌─────────────────────┐         ┌─────────────────────┐         ┌─────────────────────┐
│  MetricCalculator   │         │  SearchTermClassify │         │   Recommendation    │
│       Service       │         │      Service        │         │      Service        │
│                     │         │                     │         │                     │
│  - CTR, CPC, CVR    │         │   - Term classification│       │   - Approval-based  │
│  - ACOS, ROAS       │         │   - Keyword vs ASIN │         │   - Risk assessment │
│  - Validation       │         │   - Low-data flag   │         │   - Explanation     │
└─────────────────────┘         └─────────────────────┘         └─────────────────────┘
                                                                         │
                                                                         ▼
┌─────────────────────┐         ┌─────────────────────┐         ┌─────────────────────┐
│   CampaignPlan      │         │  NegativeKeyword    │         │    BulkExport       │
│       Service       │         │      Service        │         │      Service        │
│                     │         │                     │         │                     │
│   - Draft builder   │         │   - Exact/Phrase    │         │   - Bulk sheet      │
│   - Budget grouping │         │   - Preview         │         │   - Export only     │
│   - Naming          │         │   - Overblocking    │         │   - After approval  │
└─────────────────────┘         └─────────────────────┘         └─────────────────────┘
                                                                         │
                                                                         ▼
┌─────────────────────┐         ┌─────────────────────┐         ┌─────────────────────┐
│    Monitoring       │         │     AuditLog        │         │   RiskPolicyValid   │
│       Service       │         │      Service        │         │     -Validator      │
│                     │         │                     │         │                     │
│  - Performance      │         │   - Decision logging│         │   - Safe action     │
│  - Learning         │         │   - Audit trail     │         │   - Risk labels     │
│  - Feedback         │         │   - Rule version    │         │   - Blocked reasons │
└─────────────────────┘         └─────────────────────┘         └─────────────────────┘
```

### 1.2 Service Boundaries

All decision-making services should support deterministic rules and AI-powered reasoning through the `DualPathDecisionService[T]` pattern, with deterministic fallback.

| Service | Responsibility | Output |
|---------|----------------|--------|
| **FileUploadService** | Creates workspace-scoped upload records, validates metadata, stores raw files, and queues parsing | Upload record with status, file metadata |
| **ReportParserService** | Parses CSV/XLS/XLSX safely without executing formulas or trusting spreadsheet instructions | Parsed data rows, row count, parsing errors |
| **ReportValidationService** | Detects report type, required columns, hidden header issues, marketplace/currency/date mismatches, duplicate rows, and unsafe data | Validation result with blocking errors and warnings |
| **MetricCalculatorService** | Normalizes numeric metrics and recalculates CTR, CPC, CVR, ACOS, and ROAS | Normalized rows with recalculated metrics |
| **SearchTermClassifierService** | Classifies terms as keyword, ASIN/product target, branded, competitor, generic, irrelevant, low-data, or duplicate | Classification with confidence and reasons |
| **RecommendationService** | Generates approval-required recommendations from normalized evidence | Recommendations with action type, risk level, explanation |
| **RiskPolicyValidatorService** | Blocks unsafe actions and attaches risk labels and blocked reasons | Risk assessment with blocked reasons |
| **CampaignPlanService** | Builds campaign plan drafts from approved recommendations or approved keyword sets | Campaign plan draft with structure, budgets, safety summary |
| **NegativeKeywordService** | Previews negative exact/phrase candidates before approval/export | Negative keyword preview with risk impact analysis |
| **BulkExportService** | Generates Amazon bulk sheet exports only after approval | Export file, export metadata, audit log entry |
| **MonitoringService** | Imports later performance reports and evaluates outcomes | Monitoring import with comparison to recommendations |
| **AuditLogService** | Records every customer-impacting decision and workflow transition | Audit log with workspace, actor, entity type, entity id |

### 1.3 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Runtime | Python 3.11+ with FastAPI | Async I/O for file processing, large dataset handling |
| Database | PostgreSQL 15 | ACID compliance, JSON support for flexible schemas |
| ORM | SQLAlchemy / Prisma | Type-safe database operations |
| Storage | AWS S3 (or local dev) | Uploads, processed files, backups |
| Auth | JWT + Refresh Tokens | Stateless auth with rotation |
| Validation | Pydantic | Type-safe schema validation |
| AI/Reasoning | OpenAI / Claude API | Bounded reasoning and explanation layer |
| Queue | Redis / PostgreSQL Jobs | Background job processing |
| Monitoring | Prometheus + Grafana | Metrics, dashboards |
| Logging | Structured Logs | Audit trail, debugging |

## 2. Database Tables

### 2.1 Core Tables (Existing)

| Table | Description |
|-------|-------------|
| `workspaces`, `workspace_members` | Workspace isolation and user membership |
| `product_profiles` | Amazon seller accounts and product profiles |
| `uploads` | File upload records with status tracking |
| `upload_parse_runs`, `upload_parsed_rows`, `upload_parse_errors` | Parsing history and errors |
| `account_imports`, `account_import_entities`, `product_mapping_suggestions` | Product catalog imports |
| `monitoring_imports`, `monitoring_snapshots` | Performance tracking data |
| `recommendations`, `recommendation_decisions` | Recommendation records with approval status |
| `campaign_plans`, `bulk_exports` | Campaign structure and export files |
| `approvals`, `audit_logs` | Human approval records and audit trail |
| `ai_runs`, `rule_versions`, `job_queue`, `outbox_events` | AI reasoning tracking and job execution |

### 2.2 New/Enhanced Tables

#### 2.2.1 `report_validation_runs`
 Stores detailed validation results for each report upload:

```python
{
  "id": "uuid",
  "workspace_id": "uuid",
  "source_upload_id": "uuid",
  "created_by": "uuid",
  "created_at": "datetime",
  
  # Validation metrics
  "validation_score": 0-100,
  "blocking_errors_count": int,
  "warnings_count": int,
  
  # Report metadata
  "report_type_detected": "sp_search_term" | "sp_campaign" | "sp_product_ad" | "sp_keyword" | "unknown",
  "marketplace_detected": "US" | "UK" | "DE" | "FR" | "JP" | "IT" | "ES" | "CA" | "MX" | "AU" | "IN",
  "currency_detected": "USD" | "GBP" | "EUR" | "JPY" | "CAD" | "AUD" | "INR" | "MXN",
  "date_range_start": "date",
  "date_range_end": "date",
  
  # Status
  "validation_status": "validated" | "blocked" | "warnings_only",
  "blocked_rules": ["list", "of", "rule_names"],
  "warnings": [
    {
      "field": "column_name",
      "message": "warning_text",
      "severity": "low" | "medium" | "high"
    }
  ],
  "confidence_score": 0-100,
  "headers_detected": ["column1", "column2"],
  "headers_missing": ["column1", "column2"],
  "has_duplicate_rows": boolean,
  "has_hidden_spaces": boolean,
  "validation_method": "deterministic" | "ai_assisted" | "hybrid"
}
```

#### 2.2.2 `normalized_report_rows`
 Canonical row storage for querying normalized metrics:
- `original_row_id`
- `normalized_impressions`, `normalized_clicks`, `normalized_spend`
- `normalized_sales`, `normalized_orders`, `normalized_units`
- `recalculated_ctr`, `recalculated_cpc`, `recalculated_cvr`
- `recalculated_acos`, `recalculated_roas`
- `metric_mismatch_flags` (JSON)

#### 2.2.3 `search_term_classifications`
 Classification results for each search term:
```python
{
  "id": "uuid",
  "workspace_id": "uuid",
  "source_row_id": "uuid",
  "created_at": "datetime",
  
  "search_term": "string",
  "classification_type": "keyword" | "asin" | "branded" | "competitor" | "generic" | "irrelevant" | "low_data" | "duplicate",
  "confidence_score": 0-100,
  "reasons": ["reason1", "reason2"],
  "classifier_version": "1.0.0",
  "normalized_term": "normalized_search_term"
}
```

#### 2.2.4 `negative_keyword_previews`
 Preview records for negative keyword candidates:
```python
{
  "id": "uuid",
  "workspace_id": "uuid",
  "preview_set_id": "uuid",
  "created_by": "uuid",
  "created_at": "datetime",
  
  "search_term": "string",
  "match_type": "exact" | "phrase",
  "campaign_ids": ["uuid1", "uuid2"],
  
  # Performance metrics
  "impressions_confirmed": int,
  "clicks_confirmed": int,
  "spend_confirmed": decimal,
  "orders_confirmed": int,
  "sales_confirmed": decimal,
  
  # Estimated impact
  "estimated_spend_savings": decimal,
  "estimated_sales_impact": decimal,
  
  # Risk assessment
  "risk_label": "low" | "medium" | "high" | "critical",
  "risk_factors": ["factor1", "factor2"],
  "overblocking_risk": boolean,
  
  # Approval tracking
  "approval_status": "pending" | "approved" | "rejected" | "applied",
  "approved_by": "uuid",
  "approved_at": "datetime",
  "rejection_reason": "string"
}
```

#### 2.2.5 `budget_confirmations`
 Budget approval tracking:
```python
{
  "id": "uuid",
  "workspace_id": "uuid",
  "campaign_plan_id": "uuid",
  "created_by": "uuid",
  "created_at": "datetime",
  
  "total_daily_exposure": decimal,  # Sum of all ad group budgets
  "total_monthly_exposure": decimal,  # 30-day projection
  "approver_id": "uuid",
  "approval_note": "string",  # Required field
  "confirmation_timestamp": "datetime",
  
  "approved_ad_groups": [
    {
      "ad_group_id": "uuid",
      "name": "string",
      "budget": "decimal"
    }
  ]
}
```

#### 2.2.6 `recommendation_exports`
 Links recommendations to exports:
```python
{
  "id": "uuid",
  "workspace_id": "uuid",
  "export_id": "uuid",
  "recommendation_id": "uuid",
  "created_at": "datetime",
  
  "export_row_number": int,
  "export_action_type": "add_negative_exact" | "add_negative_phrase" | "remove_asin" | "pause_ad_group",
  "original_recommendation_type": "string",
  "export_metadata": {}
}
```

### 2.3 Security Requirements

Every workspace-owned table must include:
- `workspace_id` (foreign key to workspaces)
- `created_by` (UUID, user reference)
- `created_at` (timestamp with default NOW())

All workspace-owned tables must be covered by:
- **RLS (Row Level Security)** policies for workspace isolation
- **API role checks** (admin, editor, viewer permissions)
- **Audit logging** for all read/write operations

## 3. API Endpoints

### 3.1 Authentication & User Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/v1/auth/login` | Login (returns JWT + refresh) | No |
| POST | `/v1/auth/refresh` | Refresh access token | No |
| POST | `/v1/auth/logout` | Revoke refresh token | Yes |
| GET | `/v1/users/me` | Get current user profile | Yes |
| GET | `/v1/workspaces` | List user's workspaces | Yes |
| POST | `/v1/workspaces` | Create new workspace | Yes |

### 3.2 Product & Profile Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/v1/workspaces/{workspace_id}/product-profiles` | List product profiles | Yes |
| POST | `/v1/workspaces/{workspace_id}/product-profiles` | Link Amazon Ads profile | Yes |
| GET | `/v1/workspaces/{workspace_id}/product-profiles/{id}` | Get profile details | Yes |
| POST | `/v1/workspaces/{workspace_id}/product-profiles/{id}/sync` | Trigger data sync | Yes |

### 3.3 Upload & Validation API

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/v1/workspaces/{workspace_id}/uploads` | Upload report file | Yes |
| GET | `/v1/workspaces/{workspace_id}/uploads` | List uploads (pagination, filters) | Yes |
| GET | `/v1/workspaces/{workspace_id}/uploads/{id}` | Get upload status and details | Yes |
| POST | `/v1/workspaces/{workspace_id}/uploads/{id}/validate-report` | Run deterministic validation | Yes |
| POST | `/v1/workspaces/{workspace_id}/uploads/{id}/normalize-metrics` | Create normalized metric rows | Yes |
| GET | `/v1/workspaces/{workspace_id}/uploads/{id}/validation-results` | Get validation results | Yes |
| POST | `/v1/workspaces/{workspace_id}/uploads/{id}/reprocess` | Reprocess failed upload | Yes |

### 3.4 Search Term Classification

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/v1/workspaces/{workspace_id}/normalized-imports/{id}/classify-search-terms` | Classify search terms | Yes |
| GET | `/v1/workspaces/{workspace_id}/search-term-classifications` | List classifications | Yes |
| POST | `/v1/workspaces/{workspace_id}/search-term-classifications/{id}/override` | Override classification | Yes |

### 3.5 Recommendation Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/v1/workspaces/{workspace_id}/recommendations/generate` | Generate recommendations for upload | Yes |
| GET | `/v1/workspaces/{workspace_id}/recommendations` | List recommendations (filters, pagination) | Yes |
| GET | `/v1/workspaces/{workspace_id}/recommendations/{id}` | Get recommendation details | Yes |
| GET | `/v1/workspaces/{workspace_id}/recommendations/{id}/why` | Get explanation, evidence, risk labels | Yes |
| POST | `/v1/workspaces/{workspace_id}/recommendations/{id}/approve` | Approve recommendation (creates audit) | Yes |
| POST | `/v1/workspaces/{workspace_id}/recommendations/{id}/reject` | Reject recommendation (requires reason) | Yes |
| POST | `/v1/workspaces/{workspace_id}/recommendation-sets/{id}/negative-keyword-preview` | Build negative exact/phrase preview | Yes |

### 3.6 Campaign Plan Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/v1/workspaces/{workspace_id}/recommendation-sets/{id}/campaign-plan` | Create campaign plan draft | Yes |
| GET | `/v1/workspaces/{workspace_id}/campaign-plans` | List campaign plans | Yes |
| GET | `/v1/workspaces/{workspace_id}/campaign-plans/{id}` | Get plan details | Yes |
| PATCH | `/v1/workspaces/{workspace_id}/campaign-plans/{id}` | Update plan draft | Yes |
| POST | `/v1/workspaces/{workspace_id}/campaign-plans/{id}/confirm-budget` | Record budget confirmation | Yes |
| POST | `/v1/workspaces/{workspace_id}/campaign-plans/{id}/exports` | Generate bulk sheet export | Yes |
| GET | `/v1/workspaces/{workspace_id}/campaign-plans/{id}/export/download` | Download bulk sheet file | Yes |

### 3.7 Monitoring & Learning

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/v1/workspaces/{workspace_id}/products/{id}/monitoring-imports` | Import performance report | Yes |
| GET | `/v1/workspaces/{workspace_id}/monitoring-imports` | List monitoring imports | Yes |
| GET | `/v1/workspaces/{workspace_id}/monitoring-imports/{id}` | Get import details | Yes |
| POST | `/v1/workspaces/{workspace_id}/monitoring-imports/{id}/analyze` | Compare to recommendations | Yes |
| GET | `/v1/workspaces/{workspace_id}/monitoring/dashboard` | Get dashboard summary | Yes |

### 3.8 Audit & Jobs

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/v1/workspaces/{workspace_id}/audit-logs` | List audit logs (filters, pagination) | Yes |
| GET | `/v1/workspaces/{workspace_id}/approvals` | List approvals (filters, pagination) | Yes |
| GET | `/v1/workspaces/{workspace_id}/approvals/{id}` | Get approval details | Yes |
| GET | `/v1/workspaces/{workspace_id}/jobs` | List background jobs | Yes |
| POST | `/v1/workspaces/{workspace_id}/jobs/{id}/cancel` | Cancel job | Yes |

## 4. File Upload Validation Pipeline
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
