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

The Agent Control Center has moved toward a multi-agent operations interface: upload-first report analysis, Agent Team Dashboard, non-drag Visual Workflow Canvas, right Agent Inspector, Trace Timeline, Human Approval Checkpoints, Simple/Advanced Mode, and template presets. The UI must continue to show that recommendations are recommendation-only, require human approval, and do not execute live Amazon Ads changes.

## Backend Orchestration Roadmap

Phase A is underway. Account imports now create durable workflow records, workflow trace events, and a LangGraph-compatible local graph path. Next work should move DeepSeek recommendation generation and approval gate persistence fully inside the graph, then move graph execution out of the API request through the queue abstraction.

## Account-Level Bulk Analysis Roadmap

### Phase 1
- Add account-level upload mode and workspace-only upload path.
- Detect report type from headers and sample rows.
- Store `account_imports`, `account_import_entities`, and `product_mapping_suggestions`.
- Group parsed rows by account, product, campaign, ad group, target, and search term.
- Show upload-first flow in Agent Control Center.

### Phase 2
- Extend agent configs for provider/model labels, strictness, scope toggles, risk controls, output controls, and chunking limits.
- Add deterministic account-import Run Analysis endpoint that creates agent runs, traceable workflow output, and approval-only recommendations from grouped report entities.
- Pass safe config and grouped metrics into AI prompts.
- Add account-level AI Recommendation Brain runs.

### Phase 3
- Build product mapping confirmation UI.
- Deepen Agent Control Center configuration editing and connect every safe config field to backend persistence.
- Expand grouped recommendation dashboard filters for account import, product, ASIN, campaign, ad group, type, priority, confidence, agent, and approval status.
- Add interaction-level tests for node selection, inspector editing, timeline expansion, approval actions, and pause/resume/stop/rerun controls.

### Phase 4
- Add large-report chunking by product, campaign, or entity priority.
- Validate AI output per chunk and combine accepted recommendations.
- Expand backend, frontend, and E2E coverage.
