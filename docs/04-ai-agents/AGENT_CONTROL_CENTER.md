# Agent Control Center

## Purpose
The Agent Control Center gives workspace users visibility and control over AdSurf's multi-agent recommendation workflow. The primary entry point is now account-level report upload before agent analysis. Users can inspect agent responsibilities, inputs, outputs, event timelines, workflow edges, related recommendations, and safety boundaries.

The page is designed for sellers and agency operators, not as a developer-only node builder. It combines an Agent Team Dashboard, a non-drag Visual Workflow Canvas, a Trace Timeline, Human Approval Checkpoints, and a right-side Agent Inspector.

## Safety Boundary
Agents may analyze uploaded Amazon Ads report data and create recommendation outputs. Agents must not execute live Amazon Ads changes, approve or reject recommendations, bypass human approval, disable audit logging, hide evidence, or delete source uploads.

Approval only updates app state and audit logs or prepares manual/export instructions. No Agent Control Center action calls Amazon Ads mutation APIs.

## Agents
| Agent | Responsibility |
| --- | --- |
| Report Upload Node | Receives account reports or bulk sheets and starts the workflow. |
| Report Detection Agent | Detects report type, confidence, required columns, entity levels, and readiness. |
| Product Resolution Agent | Maps ASINs, SKUs, product names, and unknown product groups to profiles or suggestions. |
| Metrics Analysis Agent | Summarizes spend, sales, clicks, orders, ACOS, ROAS, CTR, CVR, winners, wasters, and risks. |
| AI Recommendation Brain | Uses DeepSeek or configured fallback mode to create recommendation decisions from normalized evidence. |
| Bid Optimization Agent | Reviews bid-related recommendations and explains bid action risk. |
| Negative Keyword Agent | Reviews wasted search terms and explains negative exact or phrase evidence. |
| Budget Allocation Agent | Reviews campaign and product budget pressure, budget risk, and reallocation opportunities. |
| Pause Review Agent | Reviews entities that may need pause review and explains risk. |
| Stakeholder Reporting Agent | Creates dashboard summary, executive summary, next actions, and approver notes. |
| Human Approval Agent | Routes recommendations to users and prevents automatic approval or rejection. |

## UI Model
The `/agents` page uses Simple Mode by default and Advanced Mode for operators who need deeper traceability.

| Surface | What it shows |
| --- | --- |
| Top bar | Upload/run controls, pause/resume/stop/rerun controls, approvals shortcut, and deterministic/AI/hybrid selector. |
| Left sidebar | Workspace, Reports, Agents, Workflows, Recommendations, Approvals, and Settings navigation. |
| Agent Team Dashboard | Business-friendly cards with status, task, provider/model, mode, strictness, confidence threshold, data access, context limits, permissions, recommendation count, last run, and errors. |
| Visual Workflow Canvas | Horizontal pipeline with colored nodes, data-passing edge labels, active/failed/approval states, and node selection. |
| Right Agent Inspector | Tabs for Overview, Configuration, Prompt / Business Goal, Input Data, Output, Related Recommendations, Permissions, Trace Events, and Safety. |
| Trace Timeline | Expandable execution events with provider/model, latency, cost metadata when available, validation errors, retries, and fallback details. |
| Human Approval Checkpoints | Pending recommendation cards grouped around evidence, risk, confidence, and approve/reject/edit actions. |
| Agent Templates | MVP presets for Conservative Profitability, Growth Scaling, Wasted Spend Cleanup, Launch Campaign Review, and Agency Account Audit. |

Simple Mode keeps the upload, agent status, simple workflow strip, recommendations, and safety labels visible while hiding raw JSON and deep trace details. Advanced Mode shows the canvas, inspector details, prompt/configuration, raw input/output summaries, trace logs, risk controls, and model/provider settings.

## Workflow Graph
The default account workflow is:

`Report Upload -> Report Detection Agent -> Product Resolution Agent -> Metrics Analysis Agent -> AI Recommendation Brain -> Bid Optimization / Negative Keyword / Budget Allocation / Pause Review -> Stakeholder Reporting -> Human Approval Queue`

The legacy single-product monitoring graph remains supported:

`Performance Import -> Metrics Analysis -> AI Recommendation Brain -> Bid Optimization / Negative Keyword / Pause Review -> Stakeholder Reporting -> Approval Queue`

Edges show status, timestamps when available, and summaries of data passed, such as normalized metrics, rollups, recommendation candidates, risk notes, and approval notes.

## Controls
| Control | Behavior |
| --- | --- |
| Enable/disable | Changes future workflow behavior for a workspace or product. |
| Pause/resume | Records user intent and pauses/resumes displayed run state. |
| Stop | Records user intent and prevents stopped agents from creating new outputs when checked before execution. |
| Rerun | Creates a new run record. Old runs are not overwritten. |
| Rerun from here | Queues a workflow control action from a selected agent onward. |
| Configure | Updates mode, strictness, confidence threshold, max recommendations, and recommendation-type toggles. |

The UI always labels recommendation-producing surfaces with: `Recommendation only`, `Requires human approval`, and `No live Amazon Ads change executed`.

## Configuration
Agent configs can be workspace-level, product-level, and later account-import-level:

- `enabled`
- `mode`: deterministic, ai, hybrid
- `provider`: deepseek, fallback, deterministic
- `model`
- `strictness_level`: conservative, balanced, aggressive
- `confidence_threshold`: low, medium, high
- `max_recommendations`
- `max_rows_per_ai_call`, `max_groups_per_ai_call`, `max_products_per_run`
- `analysis_depth`: quick, standard, deep
- account, product, campaign, keyword, and search-term scope toggles
- recommendation type toggles for keep-running, bid, pause review, negatives, move-to-exact, budget review, data quality, and product mapping
- risk controls for bid multipliers, pause/negative confidence, minimum clicks/spend, target ACOS, orders, and ROAS
- prompt controls for business goals, brand safety, competitors, and margin notes
- output controls for language, explanation detail, reasoning summary visibility, metric evidence, and risk notes

Owner/admin roles can configure agents. Analysts can run/rerun/control agents. Approvers and viewers can inspect outputs according to workspace read access.

No API keys or arbitrary provider secrets are exposed through agent configuration.

## Audit And Events
Every control action writes an audit log and an agent event. Events include queued, started, input prepared, model called, output received, output validated, recommendations created, paused, resumed, stopped, failed, succeeded, and skipped.

Events store agent ID, run ID when available, monitoring import ID when available, message, event type, metadata JSON, and timestamp.

## Recommendation Traceability
Agent runs store Agent Control Center metadata in run output, including agent ID, monitoring import ID, mode, strictness, confidence threshold, safety boundary, and related recommendation IDs. Recommendation evidence also stores the AI run ID/provider/model when applicable.
