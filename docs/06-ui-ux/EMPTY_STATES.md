# Empty States

| Page | Empty state message intent | Primary action |
| --- | --- | --- |
| Products | No product profiles yet | Create product profile. |
| Uploads | No research files uploaded | Upload CSV/XLSX. |
| Keywords | Upload and process a file first | Go to uploads. |
| Campaign Plans | Approve keywords to generate a plan | Review keywords. |
| Bulk Exports | Approve a campaign plan first | Open campaign plans. |
| Monitoring | Add performance data after launch | Upload report. |
| Recommendations | No recommendations need review | View monitoring. |
| Audit Log | No events recorded yet | Continue workflow. |

## Acceptance Criteria
Empty states tell customers the next useful action without explaining implementation internals.

## Error And Loading States
Loading, syncing, empty, and error states must be shown as separate states.

- Use loading copy only while a request is actively in flight, with a spinner or skeleton and `role="status"` when practical.
- Use empty-state copy only after a successful response returns no records.
- Use professional error copy for network or server failures. Do not show raw browser messages like `Failed to fetch` by themselves; include the system context and the original browser/server detail in plain language.
- Data refresh errors should offer a retry action when the user can recover without leaving the page.
