# Workflow: Monitoring 14 Days

## Steps
| Day | Owner | Behavior |
| --- | --- | --- |
| 0 | User | Upload launch or performance baseline. |
| 1-6 | Monitoring worker | Normalize daily performance snapshots. |
| 1-7 | Rule engine | Detect low spend plus low traffic and recommend 10% bid increase. |
| 7 | Rule engine | If ACOS is under 50%, recommend campaign lock for another 7 days. |
| 8-14 | Monitoring worker | Continue tracking and recommendation status. |

## Acceptance Criteria
- Metrics are stored by campaign and date.
- Recommendations include input metrics and rule name.
- No monitoring rule executes changes without approval.

