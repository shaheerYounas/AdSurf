# Agent Orchestration

## Purpose
The Agent Council turns Amazon Ads performance reports into explainable, approval-controlled recommendations. Deterministic rules create recommendation records. Agents explain evidence, priority, and stakeholder impact. Humans approve or reject every customer-impacting action.

## V1 Flow
| Step | Owner | Output |
| --- | --- | --- |
| Upload SP Search Term report | User | Raw upload and parse run. |
| Validate report shape | Performance Import Agent | Data quality notes and required-column status. |
| Normalize metrics | Monitoring worker | Campaign/ad group/targeting/search-term snapshots. |
| Calculate metrics | Metrics module | Row and rollup metrics: CTR, CPC, CVR, ACOS, ROAS, CPA, shares, waste, pressure, relevance, match-risk, and overlap signals. |
| Evaluate rules | Rule engine | Recommendation records with entity type, priority, confidence, evidence JSON, metrics, and proposed action. |
| Explain recommendations | Bid, Negative Keyword, Pause Review agents | Structured explanation JSON stored in `ai_runs`. |
| Summarize for dashboard | Stakeholder Reporting Agent | Plain-language workspace summary. |
| Approve or reject | Human user | Recommendation decision and audit log. |

## Agent Boundary
Agents may summarize, explain, rank by urgency, and call out missing data. Agents must not approve, reject, execute, export, or silently mutate recommendation status.

## Required Metadata
Every agent run stores `agent_name`, `workspace_id`, `product_id`, `provider`, `model`, `schema_version`, `input_hash`, `output_json`, `status`, `latency_ms`, and `created_at`.

## Phase 1 Agent Council
| Agent | Input | Output |
| --- | --- | --- |
| Performance Import Agent | Report metadata, required-column validation, row counts, warnings | `report_quality_summary`, `missing_columns`, `warnings`, `can_generate_recommendations`. |
| Metrics Analysis Agent | Aggregated metrics and recommendations | `performance_summary`, `top_winners`, `top_wasters`, `risk_areas`, `data_limitations`. |
| Bid Optimization Agent | Bid and budget recommendations | Explanation, why-now reason, expected effect, risk note, confidence reason. |
| Negative Keyword Agent | Negative exact/phrase recommendations | Explanation, waste evidence, negative type, risk note. |
| Pause Review Agent | Pause-review recommendations | Pause reason, evidence summary, risk note. |
| Stakeholder Reporting Agent | All recommendations and rollups | Dashboard summary, executive summary, analyst notes, approver notes, next best actions. |

## Refusal Conditions
Agents refuse or defer when report columns are missing, workspace scope is unclear, data is unparsed, recommendation evidence is absent, or a request asks the agent to bypass human approval.
