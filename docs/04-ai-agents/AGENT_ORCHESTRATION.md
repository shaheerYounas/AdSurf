# Agent Orchestration

## Purpose
The Agent Council turns Amazon Ads performance reports into explainable, approval-controlled recommendations. Deterministic code calculates metrics and rollups. DeepSeek AI may generate recommendation decisions from uploaded report evidence, and backend validators decide whether the AI JSON is safe enough to save. Humans approve or reject every customer-impacting action.

## V1 Flow
| Step | Owner | Output |
| --- | --- | --- |
| Upload SP Search Term report | User | Raw upload and parse run. |
| Validate report shape | Performance Import Agent | Data quality notes and required-column status. |
| Normalize metrics | Monitoring worker | Campaign/ad group/targeting/search-term snapshots. |
| Calculate metrics | Metrics module | Row and rollup metrics: CTR, CPC, CVR, ACOS, ROAS, CPA, shares, waste, pressure, relevance, match-risk, and overlap signals. |
| Decide recommendations | DeepSeek recommendation brain | Strict JSON recommendations with entity type, priority, confidence, evidence, reasoning summary, and proposed action. |
| Validate AI output | Backend validator | Reject unsafe JSON, invalid references, approval bypasses, live execution claims, out-of-range bid multipliers, and missing evidence. |
| Fallback when configured | Deterministic rules | `fallback_rules` recommendations if `AI_RECOMMENDATION_MODE=deterministic_fallback` or hybrid fallback is used. |
| Summarize for dashboard | DeepSeek brain or local stakeholder agent | Plain-language workspace summary. |
| Approve or reject | Human user | Recommendation decision and audit log. |

## Agent Control Center
The Agent Control Center exposes the monitoring graph, agent definitions, agent configs, run history, event timelines, and related recommendations. Users can pause, resume, stop, rerun, rerun from an agent onward, and configure agent mode/strictness/confidence threshold without granting agents permission to execute live Amazon Ads changes.

Control actions are role-protected and audited. Reruns create new agent runs and do not overwrite historical output.

## Agent Boundary
Agents may analyze uploaded report evidence and generate recommendation decisions. Agents must not approve, reject, execute, export, call Amazon Ads mutation APIs, or silently mutate recommendation status. Approval only updates app state and audit logs or prepares a later manual/export handoff.

## Required Metadata
Every agent run stores `agent_name`, `workspace_id`, `product_id`, `provider`, `model`, `schema_version`, `input_hash`, `output_json`, `status`, `latency_ms`, and `created_at`.

Agent Control Center metadata also tracks `agent_id`, `monitoring_import_id`, `input_json`, `error_json`, dependency run IDs, related recommendation IDs, mode, strictness level, confidence threshold, control actor/reason, and event timeline when available.

## Phase 1 Agent Council
| Agent | Input | Output |
| --- | --- | --- |
| Monitoring Recommendation Brain | Product profile, import metadata, normalized snapshots, deterministic metrics, rollups, warnings, guardrails | Recommendation JSON and dashboard summary. Provider `deepseek`, model from `DEEPSEEK_MODEL`. |
| Performance Import Agent | Report metadata, required-column validation, row counts, warnings | `report_quality_summary`, `missing_columns`, `warnings`, `can_generate_recommendations`. |
| Metrics Analysis Agent | Aggregated metrics and recommendations | `performance_summary`, `top_winners`, `top_wasters`, `risk_areas`, `data_limitations`. |
| Bid Optimization Agent | Bid and budget recommendations | Explanation, why-now reason, expected effect, risk note, confidence reason. |
| Negative Keyword Agent | Negative exact/phrase recommendations | Explanation, waste evidence, negative type, risk note. |
| Pause Review Agent | Pause-review recommendations | Pause reason, evidence summary, risk note. |
| Stakeholder Reporting Agent | All recommendations and rollups | Dashboard summary, executive summary, analyst notes, approver notes, next best actions. |

## Refusal Conditions
Agents refuse or defer when report columns are missing, workspace scope is unclear, data is unparsed, recommendation evidence is absent, DeepSeek is unavailable in required-AI mode, JSON validation fails, or a request asks the agent to bypass human approval or execute live Amazon Ads changes.
