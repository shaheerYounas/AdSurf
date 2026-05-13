# Workflow: Keywords To Campaigns

## Steps
| Step | Owner | Output |
| --- | --- | --- |
| Load approved keywords | API | Frozen approved set. |
| Select Hero keyword | Rule engine | Highest relevance, volume tie-break. |
| Batch remaining terms | Rule engine | Groups of 5 to 7. |
| Generate campaigns | Campaign worker | Exact, Phrase, Broad structures. |
| Generate negatives | Campaign worker | Negative Exact and Negative Phrase rows. |
| Explain plan | Campaign Builder Agent | Review summary. |
| Approve plan | User | Plan approved for export. |

## Acceptance Criteria
- No rejected term appears in plan.
- Every approved non-Hero keyword is grouped once.
- Campaign plan cannot be exported until approved.

