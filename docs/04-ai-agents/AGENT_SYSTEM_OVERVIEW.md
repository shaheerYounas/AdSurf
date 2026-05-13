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
agent_name, tenant_id, input_hash, provider, model, schema_version, output_json, status, latency_ms, created_at.

