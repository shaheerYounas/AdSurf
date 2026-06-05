# Workflow: Performance Report To Recommendations

## Steps
| Step | Responsible party | Behavior |
| --- | --- | --- |
| 1 | User | Upload or select a processed Sponsored Products Search Term report. |
| 2 | Monitoring worker | Validate required report columns and data quality. |
| 3 | Monitoring worker | Normalize campaign, ad group, targeting, search-term, and metric snapshots. |
| 4 | Metrics module | Calculate campaign, ad-group, target, search-term, and report-level performance rollups. |
| 5 | DeepSeek recommendation brain | Generate keep-running, bid, pause-review, negative, move-to-exact, watch-lock, budget-review, and data-quality recommendations from structured report evidence. |
| 6 | Backend validator | Validate strict JSON, entity references, approval flags, safe bid multipliers, negative match type, evidence, and no live Amazon Ads mutation instructions. |
| 7 | Fallback rules when configured | Use deterministic recommendations only in configured fallback/hybrid modes if DeepSeek fails. |
| 8 | Agent council | Store `ai_runs` for DeepSeek recommendation generation, fallback failures, or local explanation summaries. |
| 9 | Human approver | Approve or reject recommendations with notes. |

## Import Idempotency
One upload can create only one monitoring import for the same workspace, product, upload, and report type. Repeated import requests return the existing import with copy equivalent to:

`This upload was already imported. View the existing import or explicitly re-run analysis.`

Intentional re-analysis must reuse the existing import record; it must not create duplicate monitoring import rows.

## Import Health Severity
Monitoring import messages use severity levels:

| Severity | Meaning |
| --- | --- |
| info | Normal mapping or context note, such as Amazon column aliases mapped successfully or low-data rows. |
| warning | Reviewable issue that does not block deterministic analysis, such as optional metric mismatch or multi-product report detection. |
| error | Required input or parsing problem that prevents reliable analysis. |
| critical | Data corruption or mathematically impossible metrics that make a row untrustworthy. |

Known Amazon column aliases are info messages, not warnings. Blank ACOS/ROAS with zero sales is normal and must not be counted as a data-quality warning.

## Product Detection
The monitoring import detects advertised product groups from product-owned columns only: Advertised ASIN, Advertised SKU, campaign-owned ASIN, or equivalent reliable product identifiers. Customer Search Term ASINs are never used to create or infer product profiles.

When multiple advertised product groups are detected, the UI must show a multi-product warning with rows, spend, sales, and orders by group so the user can decide whether to import all rows under the current product, split by detected product, create missing profiles, or manually map campaigns.

## Dashboard Summary
The monitoring dashboard must distinguish report rows from recommendations:

`1,077 report rows analyzed. 500 recommendations generated for human review. No Amazon Ads changes have been made.`

It must also show spend reviewed, sales attributed, account ACOS, zero-order spend, actionable recommendation count, watch/monitoring insights, data-quality checks, budget review notes, and detected product groups.

## Marketing Plan 14-Day Cycle
| Window | Deterministic behavior |
| --- | --- |
| Days 1-7 | If campaign spend is below daily budget, prepare a pending 10% bid-increase recommendation. Repeat daily until budget is consumed or Day 7 is reached. |
| Day 7 | Calculate cumulative ACOS as seven-day spend divided by seven-day sales. |
| Days 8-14 | If Day 7 ACOS is under 50%, lock the campaign in watch mode and suppress new bid, negative, or pause recommendations until Day 14. |

## Acceptance Criteria
- Metrics are stored by campaign and date.
- Recommendations include input metrics, decision source, AI provider/model when present, evidence JSON, proposed action, reasoning summary, confidence, priority, and approval requirement.
- AI may generate recommendation decisions from uploaded evidence, but backend validation must pass before saving.
- Approval does not mutate live Amazon Ads accounts; it only updates app state and audit logs.
- The deterministic 14-day cycle may simulate daily monitoring for preview, but every customer-impacting action remains approval-gated.
