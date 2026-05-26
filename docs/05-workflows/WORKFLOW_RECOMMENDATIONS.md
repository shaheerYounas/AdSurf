# Workflow: Recommendations

## Recommendation Types
| Type | Trigger | Approval requirement |
| --- | --- | --- |
| keep_running | No higher-priority monitoring rule triggers | Required |
| increase_bid | Low impressions/clicks and low spend where more data is needed | Required |
| decrease_bid | ACOS materially above target after sales exist | Required |
| pause_review | High spend or high clicks with no sales | Required |
| add_negative_exact | Search term click waste with no orders | Required |
| add_negative_phrase | Broad/phrase/auto search pattern waste with no orders | Required |
| move_to_exact | Non-exact source converts efficiently enough to isolate as exact | Required |
| watch_lock | Sales exist and ACOS is comfortably under target | Required |
| data_quality_review | Report metrics are internally inconsistent | Required |
| budget_review | Strong performance appears constrained by spend/budget pressure | Required |

## States
pending_approval, approved, rejected, superseded.

Approved means approved for manual action or later export. It does not mean the app changed Amazon Ads live.

## Evidence
Every recommendation displays rule name, normalized metric evidence, `evidence_json` rollups, proposed action, priority, explanation JSON, and the approval boundary.

`evidence_json` includes search-term, target, ad-group, campaign, and full-report performance. It also records threshold values, condition signals, duplicate/overlap signals, rule version, priority, confidence, entity type, and explicit flags showing that approval does not execute live Amazon Ads changes.

## Acceptance Criteria
- Recommendation state changes are audited.
- User can approve or reject with notes.
- AI output cannot approve, reject, execute, mutate, or make final recommendation decisions.
- MVP stops at recommendation approval; live execution remains later-version work.
