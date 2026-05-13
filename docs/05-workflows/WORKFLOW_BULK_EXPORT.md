# Workflow: Bulk Export

## Steps
| Step | Owner | Output |
| --- | --- | --- |
| Validate campaign plan | API/worker | Export readiness report. |
| Generate rows | Campaign worker | Campaign, ad group, keyword, negative rows. |
| Validate sheet | Worker | No missing required fields. |
| Request approval | API/UI | Approval task. |
| Approve export | User | Approval record and signed download access. |
| Download export | User | Amazon bulk sheet file. |

## Acceptance Criteria
- Export references approved campaign plan version.
- Generated file is stored in private tenant path.
- Export approval is logged before download handoff.

