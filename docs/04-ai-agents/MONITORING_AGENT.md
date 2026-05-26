# Monitoring Agent

## Responsibility
Summarize imported campaign performance and make metric trends understandable. Phase 1 monitoring decisions are produced by deterministic rules, not by AI.

## Inputs
Monitoring snapshots with impressions, clicks, spend, sales, orders, CPC, CTR, CVR, and ACOS.

## Prohibited
- Do not create final optimization decisions.
- Do not override rule-generated recommendation types, priorities, or evidence.
- Do not change bids, budgets, or campaign states.
- Do not call Amazon Ads mutation APIs.

## Acceptance Criteria
Summaries identify metric direction, data gaps, and rule-triggered recommendation status. Recommendation records must include deterministic evidence JSON before any explanation is displayed.
