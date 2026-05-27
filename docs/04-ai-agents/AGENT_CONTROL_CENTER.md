# Agent Control Center

## Purpose
The Agent Control Center gives workspace users visibility and control over monitoring agents. Users can inspect agent responsibilities, inputs, outputs, event timelines, workflow edges, related recommendations, and safety boundaries.

## Safety Boundary
Agents may analyze uploaded Amazon Ads report data and create recommendation outputs. Agents must not execute live Amazon Ads changes, approve or reject recommendations, bypass human approval, disable audit logging, hide evidence, or delete source uploads.

Approval only updates app state and audit logs or prepares manual/export instructions. No Agent Control Center action calls Amazon Ads mutation APIs.

## Agents
| Agent | Responsibility |
| --- | --- |
| Performance Import Agent | Validates report quality, missing columns, row count, and warnings. |
| Metrics Analysis Agent | Summarizes spend, sales, clicks, orders, ACOS, ROAS, CTR, CVR, winners, wasters, and risks. |
| AI Recommendation Brain | Uses DeepSeek or configured fallback mode to create recommendation decisions from normalized evidence. |
| Bid Optimization Agent | Reviews bid-related recommendations and explains bid action risk. |
| Negative Keyword Agent | Reviews wasted search terms and explains negative exact or phrase evidence. |
| Pause Review Agent | Reviews entities that may need pause review and explains risk. |
| Stakeholder Reporting Agent | Creates dashboard summary, executive summary, next actions, and approver notes. |

## Workflow Graph
The default monitoring graph is:

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

## Configuration
Agent configs can be workspace-level or product-level:

- `enabled`
- `mode`: deterministic, ai, hybrid
- `strictness_level`: conservative, balanced, aggressive
- `confidence_threshold`: low, medium, high
- `max_recommendations`
- bid, negative keyword, pause, and budget recommendation toggles

Owner/admin roles can configure agents. Analysts can run/rerun/control agents. Approvers and viewers can inspect outputs according to workspace read access.

## Audit And Events
Every control action writes an audit log and an agent event. Events include queued, started, input prepared, model called, output received, output validated, recommendations created, paused, resumed, stopped, failed, succeeded, and skipped.

Events store agent ID, run ID when available, monitoring import ID when available, message, event type, metadata JSON, and timestamp.

## Recommendation Traceability
Agent runs store Agent Control Center metadata in run output, including agent ID, monitoring import ID, mode, strictness, confidence threshold, safety boundary, and related recommendation IDs. Recommendation evidence also stores the AI run ID/provider/model when applicable.
