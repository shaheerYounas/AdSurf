# AI Agent System Overview

## Principle
AI assists with cleaning, mapping, explaining, summarizing, and drafting. For monitoring recommendations, DeepSeek AI may generate recommendation decisions from uploaded Amazon Ads report evidence. Deterministic code still calculates raw metrics and rollups, and backend validators must accept the AI JSON before anything is saved. Humans approve customer-impacting actions.

## Agent Boundaries
| Agent | Allowed | Not allowed |
| --- | --- | --- |
| Data Cleaning | Suggest normalization and row issues | Delete source data silently |
| Column Mapping | Suggest canonical mappings | Force low-confidence mappings |
| Keyword Scoring | Explain rule outputs | Invent or override scores |
| Campaign Builder | Explain generated plan | Create campaigns outside rules |
| Negative Keyword | Explain negatives | Publish negatives live |
| Monitoring | Analyze uploaded report evidence and draft validated recommendations | Change bids or budgets |
| Optimization | Recommend approval-controlled actions | Execute recommendations |
| Reporting | Generate customer summaries | Hide rule evidence |
| Human Approval | Route decisions | Approve on behalf of users |

## Required AI Run Metadata
agent_name, workspace_id, input_hash, provider, model, schema_version, output_json, status, latency_ms, created_at.

## Agent Council For Monitoring MVP
The monitoring MVP uses an Agent Council documented in `AGENT_ORCHESTRATION.md`. The council processes Sponsored Products Search Term reports after deterministic code has normalized rows and calculated metrics. DeepSeek is the primary recommendation brain when configured; deterministic rules remain as fallback and comparison baseline.

| Agent | Primary output |
| --- | --- |
| Monitoring Recommendation Brain | Strict-schema recommendations, evidence, priority, confidence, proposed action, and dashboard summary. |
| Performance Import Agent | Report shape and data-quality explanation. |
| Metrics Analysis Agent | Spend, clicks, sales, orders, ACOS, ROAS, CTR, and CVR summaries. |
| Bid Optimization Agent | Bid increase, bid decrease, and watch-lock explanations. |
| Negative Keyword Agent | Search-term waste and negative keyword review explanations. |
| Pause Review Agent | Pause/stop review explanations for poor performers. |
| Stakeholder Reporting Agent | Dashboard summary for owners, analysts, and approvers. |

Recommendation records may come from `deepseek_ai`, `fallback_rules`, or `deterministic_rules`. Status changes remain owned by human approval APIs. AI may not approve, reject, execute live Amazon Ads changes, or call Amazon Ads mutation APIs.

## Agent Control Center
The Agent Control Center documents and exposes agent registry, workflow graph, event timeline, run details, input/output JSON, related recommendations, and configuration controls. See `AGENT_CONTROL_CENTER.md`.

Owner/admin users can configure agents. Analysts can run, rerun, pause, resume, and stop agents. Approvers and viewers can inspect outputs and safety boundaries. Every control action is audited.
