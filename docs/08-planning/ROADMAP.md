# Roadmap

| Phase | Outcome |
| --- | --- |
| Foundation | Documentation, architecture, rules, and empty scaffold. |
| MVP Build | Product profiles, uploads, scoring, campaign plans, bulk export, approvals. |
| Monitoring | Uploaded Sponsored Products Search Term report analysis, deterministic metrics rollups, DeepSeek recommendation brain, strict backend validation, recommendation queue, fallback rules, Agent Control Center, reporting. |
| Monitoring Phase 2 | Stronger AI evidence drilldowns, duplicate/overlap review, workspace-level thresholds, and AI/rule comparison views. |
| Hardening | Security, RLS, audit depth, E2E coverage, deployment pipeline. |
| API Integration | Amazon Ads API read sync, then approval-controlled execution. |

## Guiding Constraint
Do not advance to live Amazon Ads execution until approval, audit, workspace isolation, and rollback patterns are proven.

## Current Monitoring Status
The current implementation is upload-analysis only. It validates processed report uploads, normalizes rows, computes deterministic metrics, asks DeepSeek for recommendation decisions when configured, validates strict JSON before saving, keeps deterministic fallback rules, stores AI run metadata, exposes the Agent Control Center for visibility/control, and shows the queue in the dashboard. It does not call Amazon Ads mutation APIs.
