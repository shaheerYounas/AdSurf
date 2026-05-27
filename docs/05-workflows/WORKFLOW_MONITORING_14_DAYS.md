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

## Acceptance Criteria
- Metrics are stored by campaign and date.
- Recommendations include input metrics, decision source, AI provider/model when present, evidence JSON, proposed action, reasoning summary, confidence, priority, and approval requirement.
- AI may generate recommendation decisions from uploaded evidence, but backend validation must pass before saving.
- Approval does not mutate live Amazon Ads accounts; it only updates app state and audit logs.
