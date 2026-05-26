# Workflow: Bulk Export

## Steps
| Step | Responsible party | Output |
| --- | --- | --- |
| Validate campaign plan | API/worker | Export readiness report. |
| Generate rows | API rule service | Campaign, ad group, keyword, negative rows. |
| Validate sheet | API rule service | No missing required fields. |
| Request approval | API/UI | Explicit approval note before export generation. |
| Approve export | User | Audit record and download access. |
| Download export | User | Amazon bulk sheet file. |

## Acceptance Criteria
- Export references approved campaign plan version.
- Generated file is stored in private workspace path.
- Export approval is logged before download handoff.
