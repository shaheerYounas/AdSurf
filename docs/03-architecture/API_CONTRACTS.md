# API Contracts

## Contract Style
REST endpoints return JSON, use Supabase Auth bearer tokens, enforce workspace scope server-side, and write audit logs for customer-impacting state changes. Workspace-scoped resources use `workspace_id` as a path parameter.

OpenAPI must be generated from backend code later. API contract tests are required for all public routes before production release.

## Standard Envelopes
Success response:

```json
{
  "success": true,
  "data": {},
  "meta": {}
}
```

Error response:

```json
{
  "success": false,
  "error": {
    "code": "",
    "message": "",
    "details": {}
  }
}
```

## Pagination, Sorting, And Filtering
| Convention | Decision |
| --- | --- |
| Pagination query | `page`, `page_size`. |
| Pagination meta | `page`, `page_size`, `total`, `has_next`. |
| Sorting | `sort` accepts field names; prefix with `-` for descending. |
| Filtering | Use explicit query parameters such as `status`, `search`, `from_date`, `to_date`, `type`. |
| Defaults | APIs must define safe default `page_size` and maximum `page_size`. |

## Idempotency And Conflicts
| Rule | Decision |
| --- | --- |
| Header | Accept `Idempotency-Key` for uploads, scoring, approvals, campaign generation, and exports. |
| Replays | Same key and same identity payload returns the original result only when the object state is still safe to replay. |
| Conflicts | Return `409` when trying to approve an already decided recommendation or regenerate an immutable export. |
| State validation | State-changing routes validate role, workspace, object status, idempotency, and approval requirements before writes. |

## Upload Protocol
Use a signed upload URL flow for large files. The API initializes an upload, returns a signed storage target, and confirms the upload after the client completes the file transfer.

Batch 3 implements upload metadata initialization and confirmation only. It does not parse files, map columns, score keywords, generate campaign plans, or produce exports.

`POST /v1/workspaces/{workspace_id}/products/{product_id}/uploads/init`

Required header: `Idempotency-Key`.

Replay behavior: the same key in the same workspace returns the existing response only when `product_id`, `original_filename`, sanitized filename identity, `mime_type`, `file_size_bytes`, `source_type`, and `initialized` status still match. Mismatched identity or an upload that has advanced beyond `initialized` returns `409`.

Request:

```json
{
  "original_filename": "competitors.csv",
  "mime_type": "text/csv",
  "file_size_bytes": 1024,
  "source_type": "competitor_keyword_research"
}
```

Response data:

```json
{
  "upload_id": "uuid",
  "storage_path": "/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/competitors.csv",
  "upload_url": "signed or local-fake upload URL",
  "upload_url_expires_at": "ISO-8601 timestamp",
  "status": "initialized"
}
```

`POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm`

Required header: `Idempotency-Key`.

Request body may include a reserved `checksum` field, but Batch 3 does not enforce checksum validation.

Confirm behavior: only `initialized -> queued_for_processing` is allowed. A replay for an upload already `queued_for_processing` returns the existing job id when the job exists. `uploaded`, `processing`, `processed`, `failed`, and `cancelled` return `409`.

Response data:

```json
{
  "upload_id": "uuid",
  "status": "queued_for_processing",
  "job_id": "uuid"
}
```

`GET /v1/workspaces/{workspace_id}/uploads` supports optional `product_id`, `status`, `page`, and `page_size`.

`GET /v1/workspaces/{workspace_id}/uploads/{upload_id}` returns upload metadata.

Account-level upload uses the same signed/local upload flow without a product path:

`POST /v1/workspaces/{workspace_id}/uploads/init`

Supported account report source types include `account_bulk_report`, `sponsored_products_search_term_report`, `sponsored_products_targeting_report`, `sponsored_products_campaign_report`, `bulk_sheet`, and `unknown_report`.

Agent Control Center also supports a one-shot multipart account report endpoint:

`POST /v1/workspaces/{workspace_id}/uploads/report`

Request: `multipart/form-data` with a required `file` field containing a CSV, XLS, or XLSX Amazon Ads report or bulk sheet. The endpoint stores the file, queues and runs the local parser in local/test mode, creates the account import, creates a durable workflow, schedules the LangGraph workflow through the local queue adapter, and returns the same response shape as account import creation, including `workflow_id`.

Response data:

```json
{
  "import_record": {},
  "detection": {},
  "entities": [],
  "product_mapping_suggestions": [],
  "workflow_id": "uuid"
}
```

Account import endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/report-detection` | Detect report type from parsed headers/sample rows. |
| POST | `/v1/workspaces/{workspace_id}/account-imports` | Create account import, grouped entities, and product mapping suggestions from a processed upload. |
| GET | `/v1/workspaces/{workspace_id}/account-imports` | List account imports. |
| GET | `/v1/workspaces/{workspace_id}/account-imports/{account_import_id}` | Read import, entities, and mapping suggestions. |
| GET | `/v1/workspaces/{workspace_id}/account-imports/{account_import_id}/entities` | List grouped account import entities. |
| GET | `/v1/workspaces/{workspace_id}/account-imports/{account_import_id}/product-mapping-suggestions` | List pending product mapping suggestions. |

Account import creation creates a durable workflow and schedules recommendation-only graph analysis. It does not run live Amazon Ads actions, approve/reject recommendations, or generate exports.

Competitor-direct phase endpoints:

| Phase | Route | Purpose |
| --- | --- | --- |
| Phase 1 | `POST /v1/workspaces/{workspace_id}/competitor-uploads` | Upload and clean competitor research CSV. |
| Phase 1 | `POST /v1/workspaces/{workspace_id}/competitor-uploads/{upload_id}/score` | Deterministically score competitor rank columns. |
| Phase 1 | `POST /v1/workspaces/{workspace_id}/competitor-uploads/{upload_id}/verify-agentic` | Verify approved terms with the Amazon browser evidence agent. |
| Phase 1 fallback | `POST /v1/workspaces/{workspace_id}/competitor-uploads/{upload_id}/verify` | Verify approved terms from provided structured or pasted evidence. |
| Phase 2 | `POST /v1/workspaces/{workspace_id}/competitor-uploads/{upload_id}/generate-campaigns` | Prepare campaign rows from `approved + verified` terms only. |
| Phase 3 | `POST /v1/workspaces/{workspace_id}/monitoring/14day-simulation` | Preview deterministic 14-day monitoring recommendations. |

Primary competitor verification request:

```json
{
  "competitors": [
    { "name": "Acme Coffee", "asin": "B0ACME1111" },
    "Bean Lab"
  ],
  "required_match_count": 3,
  "max_keywords": 25,
  "marketplace": "US",
  "headless": true
}
```

`verify-agentic` opens Amazon search result pages through a bounded browser automation agent, extracts visible title/ASIN evidence for the top 15 results, stores that evidence, and then uses deterministic verification. It does not log in, bypass CAPTCHA/browser challenges, use stealth plugins, call PAAPI, mutate Amazon Ads, approve an export, or bypass human approval. If browser automation is unavailable or Amazon returns a challenge, the endpoint fails with an auditable error instead of bypassing it.

Local operation requires Python Playwright and a Chromium browser install: `python -m pip install playwright` and `python -m playwright install chromium`.

The fallback verification endpoint accepts either structured evidence rows or pasted evidence rows:

```json
{
  "competitors": [
    { "name": "Acme Coffee", "asin": "B0ACME1111" },
    "Bean Lab"
  ],
  "evidence_text_rows": [
    {
      "search_term": "coffee beans",
      "pasted_results": "1. Acme Coffee organic whole beans B0ACME1111\n2. Bean Lab medium roast B0BEAN2222"
    }
  ],
  "required_match_count": 3,
  "verification_method": "manual_amazon_search"
}
```

`manual_amazon_search` is a fallback mode for externally provided evidence. The service parses at most the top 15 lines per term, matches original competitors by ASIN or name inside titles, stores the evidence, and returns `verified` only when the required distinct competitor count is met.

Workflow endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}` | Read workflow status, current node, progress, state summary, and latest events. |
| GET | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}/events` | Read the workflow trace timeline. |
| POST | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}/pause` | Pause a workflow record with an audited reason. |
| POST | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}/resume` | Resume an account-import workflow through the queue adapter. |
| POST | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}/stop` | Stop a workflow record with an audited reason. |
| POST | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}/rerun` | Rerun an account-import workflow through the queue adapter. |
| GET | `/v1/workspaces/{workspace_id}/approval-gates` | List human approval gates, optionally filtered by status. |
| POST | `/v1/workspaces/{workspace_id}/approval-gates/{gate_id}/approve` | Record a human gate approval. |
| POST | `/v1/workspaces/{workspace_id}/approval-gates/{gate_id}/reject` | Record a human gate rejection. |

Batch 4 parse read endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs` | List parse runs for an upload. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}` | Get parse run metadata. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/rows` | Paginated parsed rows. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/errors` | Paginated parse errors. |

Rows and errors use `page` and `page_size`. These endpoints require workspace membership and use the standard response envelope. They expose parsed row data and safe parse errors only, never storage credentials.

Batch 5 column discovery and manual mapping endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile` | Generate or return the existing deterministic column profile for the latest succeeded parse run. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile` | Read the profile and discovered columns. |
| POST | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings` | Validate and save a manual mapping snapshot. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings` | List manual mapping snapshots for the upload. |
| POST | `/v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/approve` | Approve a valid mapping and supersede prior approved mappings for the same profile. |

Column profile generation requires `owner`, `admin`, or `analyst`. Profile reads use upload read roles. Mapping create/update/approval requires `owner`, `admin`, or `analyst`; `viewer` and `approver` cannot create or approve mappings in Batch 5.

Manual mapping request:

```json
{
  "column_profile_id": "uuid",
  "mapping_json": {
    "search_term": "column_name_or_id",
    "search_volume": "column_name_or_id",
    "competitor_rank_columns": ["column_name_or_id"]
  }
}
```

Batch 5 saves `valid` and `invalid` manual mappings with validation messages. Warnings and errors are stored in `validation_errors_json` with a `severity` field. Approval does not trigger keyword scoring, campaign generation, exports, monitoring, recommendations, or Amazon Ads API work.

Batch 6 deterministic keyword relevance scoring endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/score` | Score parsed rows using an approved manual mapping. |
| GET | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}` | Read scoring run metadata and counts. |
| GET | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates` | List paginated keyword candidates. |

Scoring requires `owner`, `admin`, or `analyst`, an approved mapping, and `Idempotency-Key`. Replaying the same key for the same mapping returns the original scoring run summary. Reusing the same key for another mapping returns `409`. `viewer` and `approver` can read scoring runs/candidates where upload reads are allowed, but cannot trigger scoring.

Scoring response data:

```json
{
  "scoring_run_id": "uuid",
  "status": "succeeded",
  "total_rows": 10,
  "scored_rows": 8,
  "approved_count": 4,
  "rejected_count": 4,
  "error_count": 2
}
```

Candidate list filters: `scoring_status`, `min_relevance_score`, `max_relevance_score`, `search_term`, `page`, and `page_size`.

Batch 6 calculates only deterministic relevance scores. It does not perform semantic relevance judgment, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API work.

Batch 7 keyword review and approved keyword set endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/v1/workspaces/{workspace_id}/keyword-candidates/{candidate_id}/override` | Manually approve or reject a scored candidate with a required reason. |
| GET | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates/review` | List candidates with original status, effective status, and override info. |
| POST | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/approved-keyword-sets` | Create a locked approved keyword set snapshot from effective approved candidates. |
| GET | `/v1/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}` | Read approved keyword set summary. |
| GET | `/v1/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}/items` | List approved keyword set snapshot items. |

Overrides require `owner`, `admin`, or `analyst`. `viewer` and `approver` can read review data where workspace reads are allowed, but cannot create overrides or keyword set snapshots in Batch 7.

Override request:

```json
{
  "override_action": "approve",
  "reason": "Manual review found this term relevant."
}
```

Review list filters: `effective_status`, `original_status`, `has_override`, `min_relevance_score`, `max_relevance_score`, `search_term`, `page`, and `page_size`.

Approved keyword set request:

```json
{
  "name": "May reviewed keywords"
}
```

Approved keyword sets copy effective approved candidates into immutable snapshot items. Error candidates are excluded. A scoring run with zero effective approved candidates returns `409`. Creating a keyword set does not automatically trigger campaign generation.

Batch 8 campaign planning endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/campaign-plans` | Generate a campaign plan from a locked approved keyword set. |
| GET | `/v1/workspaces/{workspace_id}/campaign-plans/{plan_id}` | Read generated plan structure, groups, campaigns, and negatives. |
| POST | `/v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/approve` | Approve a generated campaign plan with an explicit note. |

Campaign plan creation requires `owner`, `admin`, or `analyst`, a product in the same workspace, and a locked approved keyword set for that product. Plans are generated from deterministic rules only. Campaign plan approval writes an audit event and is required before export.

Batch 9 bulk export endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/exports` | Generate an approved CSV bulk sheet from an approved campaign plan with a separate export approval note. |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}` | Read export metadata and download URL. |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}/download` | Download the stored CSV export if workspace access is allowed. |

Bulk export generation requires an already approved campaign plan and a separate non-empty export approval note. Export rows are stored through the configured storage adapter and no Amazon Ads API execution occurs.

Batch 10 monitoring and recommendation endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/workspaces/{workspace_id}/dashboard-summary` | Single-request dashboard payload with product count/list, upload counts, pending recommendation count, and top recommendations. |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports` | Create or return the existing monitoring import for a processed Sponsored Products Search Term report upload and enqueue rule evaluation only for a new import. |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/monitoring/imports` | Alias for monitoring import creation. |
| POST | `/v1/workspaces/{workspace_id}/monitoring/imports/{import_id}/run-analysis` | Requeue a queued or failed monitoring import analysis job. |
| GET | `/v1/workspaces/{workspace_id}/products/{product_id}/monitoring` | Read monitoring import status, recommendation counts, top recommendations, and latest deterministic stakeholder summary. |
| GET | `/v1/workspaces/{workspace_id}/products/{product_id}/monitoring/summary` | Alias for product monitoring summary. |
| GET | `/v1/workspaces/{workspace_id}/recommendations` | List recommendation queue with optional product, status, and type filters. |
| GET | `/v1/workspaces/{workspace_id}/products/{product_id}/recommendations` | List recommendations scoped to one product. |
| GET | `/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}` | Read one recommendation with evidence and explanation JSON. |
| POST | `/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/approve` | Approve a recommendation for manual action/export later with a required note. |
| POST | `/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/reject` | Reject a recommendation with a required note. |
| GET | `/v1/workspaces/{workspace_id}/products/{product_id}/agent-runs` | List structured explanation and summary agent runs for a product. |

Monitoring import creation requires `owner`, `admin`, or `analyst`, a processed upload with source type `amazon_ads_sp_search_term_report`, and a succeeded parse run. One import is allowed per `workspace_id + product_id + upload_id + report_type`; duplicate create requests return the existing import with `already_imported: true` and do not create another job. Recommendation reads use workspace read roles. Recommendation decisions require `owner`, `admin`, `analyst`, or `approver`. `viewer` cannot decide recommendations.

Monitoring import request:

```json
{
  "upload_id": "uuid"
}
```

Recommendation decision request:

```json
{
  "note": "Reviewed ACOS and search term relevance; approved for manual console update."
}
```

Recommendation records expose `recommendation_type`, `entity_type`, `status`, `priority`, `confidence`, campaign/ad group/target/search-term identity, `rule_version`, `rule_name`, `current_metric_snapshot_json`, `input_metrics_json`, `evidence_json`, `proposed_action_json`, and `explanation_json`. Recommendation types are `keep_running`, `increase_bid`, `decrease_bid`, `pause_review`, `add_negative_exact`, `add_negative_phrase`, `move_to_exact`, `watch_lock`, `data_quality_review`, and `budget_review`. List reads support `page` and `page_size` with a safe default page size of 250. Approval and rejection only update app state and audit history. They do not call Amazon Ads, change bids, pause entities, add negatives, or generate a bulk sheet by themselves.

Product monitoring summary responses include `summary_metrics`, `action_recommendation_counts`, `non_action_insight_counts`, `issue_counts`, and `detected_product_groups` in addition to imports, recommendation counts, top recommendations, and latest agent summary. `summary_metrics` must distinguish report rows from recommendations and include total spend, total sales, overall ACOS, zero-order spend, actionable recommendations, watch insights, data-quality checks, budget review notes, detected products, and no-live-change flags.

Local/test dev helper:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/v1/dev/process-upload-jobs` | Run queued upload parsing jobs in the API process for local in-memory demos. Disabled outside `local` and `test`. |
| POST | `/v1/dev/process-monitoring-jobs` | Run queued monitoring import jobs in the API process for local demos. Disabled outside `local` and `test`. |

## Batch 2 Auth And Product Profile Behavior
| Behavior | Decision |
| --- | --- |
| Missing auth | Return 401. |
| Missing workspace membership | Return 403. |
| Product profile write roles | owner, admin, analyst. |
| Product profile read roles | owner, admin, analyst, approver, viewer. |
| Cross-workspace product access | Return not found or forbidden; never return another workspace's product. |
| Local/test auth | Uses explicit headers only in local/test. |
| Staging/production auth | Fails closed until Supabase JWT verification is configured. |

## Bulk Product Import
Bulk product import is a two-step, approval-style workflow for internal product profiles. `POST /v1/workspaces/{workspace_id}/products/bulk-import` accepts CSV, TSV, or XLSX up to 5 MB, detects common column aliases, validates each source-numbered row, detects file duplicates and workspace conflicts, and persists a review session. This endpoint must not create or update product profiles.

`POST /v1/workspaces/{workspace_id}/products/bulk-import/{import_id}/commit` atomically claims a `ready_for_review` import before writing products. A second commit attempt returns `409 INVALID_IMPORT_STATUS` and must not create duplicate products. The request body accepts `conflict_strategy` as `skip_existing`, `update_existing`, or `create_only_missing`.

Preview summary fields include `total_rows`, `valid_rows`, `invalid_rows`, `duplicate_in_file_rows`, `already_exists_rows`, `rows_needing_review`, `exportable_valid_rows`, `rows_to_create`, `rows_to_update`, `rows_to_skip`, `warning_rows`, `detected_columns`, and up to 50 `exception_rows`. Commit responses include exact `created_count`, `updated_count`, `skipped_count`, `failed_count`, `created_product_ids`, and `updated_product_ids`.

Validation follows the product profile contract: product name is required; ASIN is normalized to uppercase and must be 10 alphanumeric characters when present; ASIN or SKU is required for import identity; target ACOS accepts `30`, `30%`, `0.30`, and `0.3` and stores a decimal percentage; budget and bid parse common currency text but must be positive with at most 4 decimal places; marketplace/currency must match supported Amazon marketplace defaults. Missing target ACOS uses the user-supplied import default when provided, otherwise the product schema default.

## Routes
| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/me` | Current user, workspaces, roles. |
| POST | `/v1/workspaces/{workspace_id}/products` | Create product profile. |
| GET | `/v1/workspaces/{workspace_id}/products` | List workspace product profiles. |
| PATCH | `/v1/workspaces/{workspace_id}/products/{product_id}` | Update product profile defaults. |
| POST | `/v1/workspaces/{workspace_id}/products/bulk-import` | Upload and validate product-profile CSV/TSV/XLSX without creating products. |
| GET | `/v1/workspaces/{workspace_id}/products/bulk-import/{import_id}` | Read a persisted bulk product import review session and source-numbered rows. |
| POST | `/v1/workspaces/{workspace_id}/products/bulk-import/{import_id}/commit` | Create/update only valid reviewed rows according to conflict strategy. |
| GET | `/v1/workspaces/{workspace_id}/products/bulk-import` | List recent bulk product import sessions. |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init` | Create upload record and signed upload URL. |
| POST | `/v1/workspaces/{workspace_id}/uploads/report` | Multipart account report upload that creates upload, import, workflow, and schedules graph analysis. |
| PUT | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/object` | Local/test browser upload object handoff before confirmation. |
| POST | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm` | Confirm upload completion and enqueue processing. |
| GET | `/v1/workspaces/{workspace_id}/uploads` | List workspace upload metadata. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}` | Get upload metadata. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs` | List upload parse runs. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}` | Get upload parse run. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/rows` | List parsed rows. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/errors` | List parse errors. |
| GET | `/v1/workspaces/{workspace_id}/jobs/{job_id}` | Get job status, progress, and user-safe errors. |
| POST | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile` | Generate deterministic column profile. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile` | Get column profile and columns. |
| POST | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings` | Save manual column mapping snapshot. |
| GET | `/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings` | List manual column mappings. |
| POST | `/v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/approve` | Approve a valid manual column mapping. |
| POST | `/v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/score` | Run deterministic keyword relevance scoring for an approved mapping. |
| GET | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}` | Get scoring run summary. |
| GET | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates` | List scoring candidates with filters. |
| POST | `/v1/workspaces/{workspace_id}/keyword-candidates/{candidate_id}/override` | Create a manual candidate override with a required reason. |
| GET | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates/review` | List review candidates with original and effective status. |
| POST | `/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/approved-keyword-sets` | Create locked approved keyword set snapshot. |
| GET | `/v1/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}` | Get approved keyword set summary. |
| GET | `/v1/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}/items` | List approved keyword set items. |
| GET | `/v1/workspaces/{workspace_id}/products/{product_id}/keywords` | Later keyword review route if split from scoring-run review. |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/keyword-sets` | Later route alias for approved keyword set snapshots. |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/campaign-plans` | Generate campaign plan from approved keyword set. |
| GET | `/v1/workspaces/{workspace_id}/campaign-plans/{plan_id}` | Review plan, groups, negatives, validation. |
| POST | `/v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/approve` | Approve campaign plan for export. |
| POST | `/v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/exports` | Generate bulk sheet from approved plan. |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}` | Export status and signed download URL if allowed. |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}/download` | Download generated CSV export if allowed. |
| POST | `/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports` | Create monitoring import from processed SP Search Term report upload. |
| GET | `/v1/workspaces/{workspace_id}/products/{product_id}/monitoring` | Monitoring import status, recommendation counts, top recommendations, and deterministic summary. |
| GET | `/v1/workspaces/{workspace_id}/recommendations` | Recommendation approval queue. |
| GET | `/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}` | Recommendation evidence detail. |
| POST | `/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/approve` | Approve recommendation. |
| POST | `/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/reject` | Reject recommendation. |
| GET | `/v1/workspaces/{workspace_id}/audit-logs` | Workspace audit log. |
| GET | `/v1/admin/health` | Health check. |

## Core Route Schemas
| Route | Request data | Response data |
| --- | --- | --- |
| `POST /v1/workspaces/{workspace_id}/products` | asin, marketplace, currency, product_name, default_daily_budget, default_bid, notes | product profile |
| `POST /v1/workspaces/{workspace_id}/products/{product_id}/uploads/init` | original_filename, mime_type, file_size_bytes, source_type | upload_id, upload_url, storage_path, upload_url_expires_at, status |
| `POST /v1/workspaces/{workspace_id}/uploads/report` | multipart `file` | account import response with workflow_id |
| `PUT /v1/workspaces/{workspace_id}/uploads/{upload_id}/object` | raw file bytes | upload metadata |
| `POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm` | checksum optional | upload_id, status, job_id |
| `GET /v1/workspaces/{workspace_id}/jobs/{job_id}` | none | job_type, status, payload_json, idempotency_key, created_at, updated_at |
| `GET /v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/rows` | page, page_size | parsed row JSON, row number, row hash |
| `GET /v1/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/errors` | page, page_size | row/file parse errors |
| `POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile` | none | column profile and profile columns |
| `POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings` | column_profile_id, mapping_json | manual mapping status, version, validation messages |
| `POST /v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/approve` | none | approved mapping snapshot |
| `POST /v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/score` | Idempotency-Key header | scoring_run_id, status, total_rows, scored_rows, approved_count, rejected_count, error_count |
| `GET /v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates` | scoring_status, min_relevance_score, max_relevance_score, search_term, page, page_size | keyword candidates with search term, search volume, score, status, and rejection reason |
| `POST /v1/workspaces/{workspace_id}/keyword-candidates/{candidate_id}/override` | override_action, reason | manual override with original and new status |
| `GET /v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates/review` | effective_status, original_status, has_override, min_relevance_score, max_relevance_score, search_term, page, page_size | candidate review rows with original status, effective status, and override info |
| `POST /v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/approved-keyword-sets` | name | locked approved keyword set summary |
| `GET /v1/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}/items` | page, page_size | approved keyword set snapshot items |
| `GET /v1/workspaces/{workspace_id}/products/{product_id}/keywords` | status, score_min, score_max, search, page, page_size | keyword candidates with score, reason, source row ids |
| `POST /v1/workspaces/{workspace_id}/products/{product_id}/keyword-sets` | keyword_candidate_ids, rejected_candidate_ids optional, override_reasons | approved_keyword_set id and version |
| `POST /v1/workspaces/{workspace_id}/products/{product_id}/campaign-plans` | approved_keyword_set_id, rule_version_id optional | campaign_plan id, status, job_id optional |
| `POST /v1/workspaces/{workspace_id}/campaign-plans/{plan_id}/exports` | approval_id or approval_note, format | export id, status, job_id |
| `GET /v1/workspaces/{workspace_id}/exports/{export_id}/download` | none | CSV file |
| `POST /v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports` | upload_id | monitoring import record, optional job_id, already_imported, message |
| `GET /v1/workspaces/{workspace_id}/products/{product_id}/monitoring` | none | imports, recommendation_counts, action_recommendation_counts, non_action_insight_counts, issue_counts, detected_product_groups, summary_metrics, top_recommendations, agent_summary |
| `GET /v1/workspaces/{workspace_id}/recommendations` | product_id, status, recommendation_type | recommendation list with evidence and explanation |
| `POST /v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/approve` | note | updated recommendation status and decision audit side effect |
| `POST /v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/reject` | note | updated recommendation status and decision audit side effect |
