# Agent Orchestration

## Purpose
The Agent Council turns Amazon Ads performance reports into explainable, approval-controlled recommendations. Deterministic rules create recommendation records. Agents explain evidence, priority, and stakeholder impact. Humans approve or reject every customer-impacting action.

## V1 Flow
| Step | Owner | Output |
| --- | --- | --- |
| Upload SP Search Term report | User | Raw upload and parse run. |
| Validate report shape | Performance Import Agent | Data quality notes and required-column status. |
| Normalize metrics | Monitoring worker | Campaign/ad group/targeting/search-term snapshots. |
| Evaluate rules | Rule engine | Recommendation records with metrics and proposed action. |
| Explain recommendations | Bid, Negative Keyword, Pause Review agents | Structured explanation JSON. |
| Summarize for dashboard | Stakeholder Reporting Agent | Plain-language workspace summary. |
| Approve or reject | Human user | Recommendation decision and audit log. |

## Agent Boundary
Agents may summarize, explain, rank by urgency, and call out missing data. Agents must not approve, reject, execute, export, or silently mutate recommendation status.

## Required Metadata
Every agent run stores `agent_name`, `workspace_id`, `provider`, `model`, `schema_version`, `input_hash`, `output_json`, `status`, `latency_ms`, and `created_at`.

## Refusal Conditions
Agents refuse or defer when report columns are missing, workspace scope is unclear, data is unparsed, recommendation evidence is absent, or a request asks the agent to bypass human approval.

