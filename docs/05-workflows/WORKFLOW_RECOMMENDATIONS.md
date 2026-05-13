# Workflow: Recommendations

## Recommendation Types
| Type | Trigger | Approval requirement |
| --- | --- | --- |
| Bid increase | Low spend plus low traffic in first 7 days | Required |
| Pause review | High spend with poor outcome | Required |
| Negative keyword review | Poor search term relevance or waste | Required |
| Campaign lock | Day 7 ACOS under 50% | Required |

## States
draft, pending_approval, approved, rejected, superseded, executed_later.

## Acceptance Criteria
- Recommendation state changes are audited.
- User can approve or reject with notes.
- MVP stops at recommendation approval; live execution remains later-version work.

