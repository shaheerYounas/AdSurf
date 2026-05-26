# Workflow: Recommendations

## Recommendation Types
| Type | Trigger | Approval requirement |
| --- | --- | --- |
| increase_bid | Low impressions/clicks and low spend where more data is needed | Required |
| decrease_bid | ACOS materially above target after sales exist | Required |
| pause_review | High spend or high clicks with no sales | Required |
| negative_keyword_review | Search term click/spend waste with no orders | Required |
| watch_lock | Sales exist and ACOS is comfortably under target | Required |

## States
pending_approval, approved, rejected, superseded.

Approved means approved for manual action or later export. It does not mean the app changed Amazon Ads live.

## Agent Evidence
Every recommendation displays rule name, metric evidence, proposed action, priority, explanation JSON, and the approval boundary.

## Acceptance Criteria
- Recommendation state changes are audited.
- User can approve or reject with notes.
- AI output cannot approve, reject, execute, or mutate recommendations.
- MVP stops at recommendation approval; live execution remains later-version work.
