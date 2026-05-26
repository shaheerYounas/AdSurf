# Product Requirements Document

## Product Summary
Amazon Ads AI Automation Control Center helps Amazon sellers and agencies convert competitor keyword research into approved Amazon Ads campaign plans, Amazon bulk sheet exports, and monitored optimization recommendations.

## Goals
| Goal | MVP requirement |
| --- | --- |
| Faster campaign creation | Convert uploaded research files into structured campaign plans. |
| Safer decisions | Reject low-relevance terms and require approval for customer-impacting actions. |
| Explainability | Show why each keyword, negative, bid recommendation, or lock is proposed. |
| Repeatability | Use deterministic rules for scoring, grouping, budgets, bids, and monitoring. |
| Agency readiness | Support multi-workspace accounts, roles, audit logs, and approval queues. |

## Primary Workflow
1. Customer creates a product profile.
2. Customer uploads competitor keyword research CSV/XLSX.
3. System cleans the file and maps columns.
4. Rule engine calculates relevance score.
5. System filters bad search terms.
6. Optional competitor presence verification is recorded as an enrichment.
7. Customer approves keyword list.
8. System generates Hero, Exact, Phrase, Broad, and negative keyword plan.
9. System generates Amazon bulk sheet export.
10. Customer approves before execution or download handoff.
11. System monitors performance for 14 days.
12. System recommends bid increases, pauses, negatives, and locks.
13. Customer controls recommendations through approval queue.
14. Later version connects to Amazon Ads API.

## Acceptance Criteria
| Area | Acceptance |
| --- | --- |
| Upload | CSV/XLSX uploads are parsed, validated, workspace-scoped, and auditable. |
| Scoring | Relevance Score exactly follows documented domain rules. |
| Campaigns | Campaign plan matches Hero/grouping/match-type/negative rules. |
| Export | Bulk sheet validates before customer approval. |
| Monitoring | 14-day recommendations are rule-generated and explainable. |
| Approval | No live or export-impacting action bypasses human approval. |
