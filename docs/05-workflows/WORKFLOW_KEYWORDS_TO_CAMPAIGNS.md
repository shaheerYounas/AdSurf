# Workflow: Keywords To Campaigns

## Steps
| Step | Responsible party | Output |
| --- | --- | --- |
| Load approved keywords | API | Frozen approved set. |
| Select Hero keyword | Rule engine | Highest relevance, volume tie-break. |
| Batch remaining terms | Rule engine | Groups of 5 to 7. |
| Generate campaigns | API rule service | Hero, Exact, Phrase, Broad structures. |
| Generate negatives | API rule service | Negative Exact and Negative Phrase rows. |
| Explain plan | API/UI | Review summary from deterministic plan JSON. |
| Approve plan | User | Plan approved for export. |

## Acceptance Criteria
- No rejected term appears in plan.
- Every approved non-Hero keyword is grouped once.
- Campaign plan cannot be exported until approved.
