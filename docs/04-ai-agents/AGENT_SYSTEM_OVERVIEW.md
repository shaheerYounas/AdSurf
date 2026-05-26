# AI Agent System Overview

## Principle
AI assists with cleaning, mapping, explaining, summarizing, and drafting. Deterministic rules calculate metrics and business decisions. Humans approve customer-impacting actions.

## Agent Boundaries
| Agent | Allowed | Not allowed |
| --- | --- | --- |
| Data Cleaning | Suggest normalization and row issues | Delete source data silently |
| Column Mapping | Suggest canonical mappings | Force low-confidence mappings |
| Keyword Scoring | Explain rule outputs | Invent or override scores |
| Campaign Builder | Explain generated plan | Create campaigns outside rules |
| Negative Keyword | Explain negatives | Publish negatives live |
| Monitoring | Summarize metric trends | Change bids or budgets |
| Optimization | Explain recommendations | Execute recommendations |
| Reporting | Generate customer summaries | Hide rule evidence |
| Human Approval | Route decisions | Approve on behalf of users |

## Required AI Run Metadata
agent_name, workspace_id, input_hash, provider, model, schema_version, output_json, status, latency_ms, created_at.

## Agent Council For Monitoring MVP
The monitoring MVP uses an Agent Council documented in `AGENT_ORCHESTRATION.md`. The council processes Sponsored Products Search Term reports after deterministic rules have created evidence-backed recommendations.

| Agent | Primary output |
| --- | --- |
| Performance Import Agent | Report shape and data-quality explanation. |
| Metrics Analysis Agent | Spend, clicks, sales, orders, ACOS, ROAS, CTR, and CVR summaries. |
| Bid Optimization Agent | Bid increase, bid decrease, and watch-lock explanations. |
| Negative Keyword Agent | Search-term waste and negative keyword review explanations. |
| Pause Review Agent | Pause/stop review explanations for poor performers. |
| Stakeholder Reporting Agent | Dashboard summary for owners, analysts, and approvers. |

The Agent Council may prioritize and explain recommendations, but recommendation records and statuses remain owned by deterministic rule code and human approval APIs.
