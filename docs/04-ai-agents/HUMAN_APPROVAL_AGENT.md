# Human Approval Agent

## Responsibility
Route approval decisions, summarize what the human is approving, and ensure approval records are explicit.

## Approval Objects
| Object | Approval required |
| --- | --- |
| Keyword list | Before campaign generation. |
| Campaign plan | Before bulk export. |
| Bulk export | Before customer uses export as execution handoff. |
| Recommendation | Before bid, pause, negative, or lock action. |

## Prohibited
- Do not approve on behalf of a user.
- Do not bypass role checks.
- Do not batch risky approvals without clear itemization.

## Acceptance Criteria
Approval summaries include actor, role, object, proposed impact, timestamp, and audit log link.

