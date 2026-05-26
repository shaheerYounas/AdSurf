# Workflow: Performance Report To Recommendations

## Steps
| Step | Responsible party | Behavior |
| --- | --- | --- |
| 1 | User | Upload or select a processed Sponsored Products Search Term report. |
| 2 | Performance Import Agent | Validate required report columns and data quality. |
| 3 | Monitoring worker | Normalize campaign, ad group, targeting, search-term, and metric snapshots. |
| 4 | Rule engine | Generate bid, pause-review, negative-keyword-review, and watch-lock recommendations. |
| 5 | Agent Council | Explain evidence and summarize stakeholder impact. |
| 6 | Human approver | Approve or reject recommendations with notes. |

## Acceptance Criteria
- Metrics are stored by campaign and date.
- Recommendations include input metrics, rule name, proposed action, agent explanation, and approval requirement.
- No monitoring rule executes changes without approval.
