# Roadmap

| Phase | Outcome |
| --- | --- |
| Foundation | Documentation, architecture, rules, and empty scaffold. |
| MVP Build | Product profiles, uploads, scoring, campaign plans, bulk export, approvals. |
| Monitoring | Uploaded Sponsored Products Search Term report analysis, metrics rollups, recommendation queue, agent explanations, reporting. |
| Monitoring Phase 2 | Stronger AI explanations, evidence drilldowns, duplicate/overlap review, and workspace-level thresholds. |
| Hardening | Security, RLS, audit depth, E2E coverage, deployment pipeline. |
| API Integration | Amazon Ads API read sync, then approval-controlled execution. |

## Guiding Constraint
Do not advance to live Amazon Ads execution until approval, audit, workspace isolation, and rollback patterns are proven.

## Current Monitoring Status
The current implementation is upload-analysis only. It validates processed report uploads, normalizes rows, computes deterministic metrics, creates approval-controlled recommendations, stores agent-run explanation JSON, and shows the queue in the dashboard. It does not call Amazon Ads mutation APIs.
