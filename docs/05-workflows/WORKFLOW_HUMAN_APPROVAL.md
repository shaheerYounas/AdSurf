# Workflow: Human Approval

## Approval Principles
| Principle | Requirement |
| --- | --- |
| Explicit | User must click an approval action with visible impact summary. |
| Role-based | Backend validates minimum role. |
| Audited | Actor, role, object, decision, timestamp, and notes are stored. |
| Reversible where possible | Rejections leave records and allow regeneration where safe. |

## Required Approval Points
- Keyword list before campaign generation.
- Campaign plan before bulk export.
- Bulk export before customer handoff.
- Recommendations before any future execution.

## Acceptance Criteria
There is no code path where AI, workers, or scheduled jobs can approve customer-impacting objects.

