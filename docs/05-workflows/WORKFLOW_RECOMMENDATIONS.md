# Workflow: Recommendations

## Recommendation Types
| Type | Trigger | Approval requirement |
| --- | --- | --- |
| keep_running | AI or fallback rules decide no stronger action is warranted | Required |
| increase_bid | AI or fallback rules identify cautious scaling potential | Required |
| decrease_bid | AI or fallback rules identify inefficient spend after sales exist | Required |
| pause_review | AI or fallback rules identify high-risk no-order spend | Required |
| add_negative_exact | AI or fallback rules identify exact search-term waste | Required |
| add_negative_phrase | AI or fallback rules identify broader wasted search patterns | Required |
| move_to_exact | AI or fallback rules identify efficient non-exact search terms | Required |
| watch_lock | AI or fallback rules decide to protect current learning/performance | Required |
| data_quality_review | AI or fallback rules identify data limitations or inconsistent metrics | Required |
| budget_review | AI or fallback rules identify budget pressure | Required |

## States
pending_approval, approved, rejected, superseded.

Approved means approved for manual action or later export. It does not mean the app changed Amazon Ads live.

## Evidence
Every recommendation displays decision source, AI provider/model when present, normalized metric evidence, `evidence_json` rollups, proposed action, priority, confidence, reasoning summary, and the approval boundary.

`evidence_json` includes search-term, target, ad-group, campaign, and full-report performance. AI recommendations also record `decision_source=deepseek_ai`, `ai_run_id`, `ai_provider`, `ai_model`, `ai_schema_version`, `ai_evidence`, and explicit flags showing that approval does not execute live Amazon Ads changes. Fallback recommendations record `decision_source=fallback_rules`.

## AI Validation
DeepSeek must return JSON only. The backend rejects output when recommendation type, entity type, priority, or confidence is invalid; referenced campaign/ad group/target/search-term values are absent from uploaded snapshots; human approval is not required; live execution is claimed; bid multipliers fall outside the safe range; negative keyword match type is missing; mutation instructions appear; or evidence/reasoning is missing.

## Acceptance Criteria
- Recommendation state changes are audited.
- User can approve or reject with notes.
- AI output can generate recommendation decisions only after backend validation.
- AI output cannot approve, reject, execute, mutate live Amazon Ads accounts, or bypass human approval.
- MVP stops at recommendation approval; live execution remains later-version work.
