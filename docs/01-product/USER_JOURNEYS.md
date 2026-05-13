# User Journeys

## Journey: Upload To Bulk Sheet
| Step | User action | System response |
| --- | --- | --- |
| 1 | Create product profile | Store tenant-scoped profile with defaults. |
| 2 | Upload CSV/XLSX | Store original file and create processing job. |
| 3 | Review column mapping | Accept or correct mapped columns. |
| 4 | Review scored keywords | Show approved/rejected terms with reasons. |
| 5 | Approve keyword list | Freeze approved set for campaign planning. |
| 6 | Review campaign plan | Show Hero, grouped campaigns, bids, budgets, negatives. |
| 7 | Approve export | Generate validated Amazon bulk sheet. |

## Journey: Monitoring To Recommendation
| Step | User action | System response |
| --- | --- | --- |
| 1 | Upload performance report | Normalize campaign metrics by day. |
| 2 | Open monitoring view | Show 14-day timeline and campaign health. |
| 3 | Review recommendations | Explain bid increases, pauses, negatives, or locks. |
| 4 | Approve or reject | Record decision and update recommendation status. |

## Journey Acceptance
- Every journey has a visible approval point before customer-impacting output.
- Every AI explanation links back to rule inputs or source data.

