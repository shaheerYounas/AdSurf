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
