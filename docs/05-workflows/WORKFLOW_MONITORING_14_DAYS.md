# Workflow: Performance Report To Recommendations

## Steps
| Step | Responsible party | Behavior |
| --- | --- | --- |
| 1 | User | Upload or select a processed Sponsored Products Search Term report. |
| 2 | Monitoring worker | Validate required report columns and data quality. |
| 3 | Monitoring worker | Normalize campaign, ad group, targeting, search-term, and metric snapshots. |
| 4 | Rule engine | Calculate campaign, ad-group, target, search-term, and report-level performance rollups. |
| 5 | Rule engine | Generate keep-running, bid, pause-review, negative, move-to-exact, watch-lock, budget-review, and data-quality recommendations. |
| 6 | Agent council | Store structured explanation-layer `ai_runs` for report quality, metrics analysis, bid optimization, negatives, pause review, and stakeholder reporting. |
| 7 | Human approver | Approve or reject recommendations with notes. |

## Acceptance Criteria
- Metrics are stored by campaign and date.
- Recommendations include input metrics, rule name, evidence JSON, proposed action, rule explanation, and approval requirement.
- No monitoring rule executes changes without approval.
