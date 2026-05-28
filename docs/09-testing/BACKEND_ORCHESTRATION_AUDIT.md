# Backend Orchestration Audit

## Purpose
This audit records the current AdSurf backend state while LangGraph orchestration is being introduced. The goal is to preserve working upload, import, recommendation, approval, and audit behavior while moving agent execution into a durable workflow system.

## Current Backend Shape

### FastAPI Routes That Already Exist
| Area | Existing routes | Notes |
| --- | --- | --- |
| Uploads | `POST /v1/workspaces/{workspace_id}/uploads/report`, `POST /v1/workspaces/{workspace_id}/uploads/init`, product upload init, `PUT /uploads/{upload_id}/object`, `POST /uploads/{upload_id}/confirm`, parse run/row/error endpoints | Agent Control Center uses the multipart report endpoint. The older init/object/confirm flow remains for product and compatibility paths. |
| Account imports | `POST /v1/workspaces/{workspace_id}/account-imports`, list/get/entities/mapping suggestions | Creates account imports from processed uploads and groups report entities. Workflow execution is queued through the local background-task adapter. |
| Agent registry/config | `GET /agents`, `GET /agent-configs`, `PATCH /agent-configs/{agent_id}` | Agent definitions/configs are API-backed and workspace-scoped. |
| Agent runs/workflow | `GET /agent-runs`, `GET /agent-runs/{id}`, legacy workflow views, plus `GET /workflows/{workflow_id}` and `/events` | Account-import analysis now writes durable LangGraph-style workflow state/events/checkpoints. Legacy Agent Control Center views still synthesize nodes from `ai_runs` for backward compatibility. |
| Agent controls | Agent-run controls plus workflow `pause`, `resume`, `stop`, and `rerun` | Records control actions and audit events. Workflow controls update durable workflow records and trace events. |
| Monitoring | `POST /products/{product_id}/monitoring-imports`, `POST /monitoring/imports/{id}/run-analysis`, product monitoring summary | Single-product monitoring worker exists and produces recommendations. |
| Recommendations | list/get recommendations, approve/reject endpoints | Approval only updates app state and audit. No live Amazon Ads mutation. |

### Services That Already Work
| Service | Current behavior |
| --- | --- |
| `report_type_detector.py` | Detects report type, confidence, missing columns, entity levels, and product identifiers. |
| `product_entity_resolver.py` | Groups account import rows by account/product/campaign/ad group/target/search term and creates mapping suggestions. |
| `upload_processing_worker.py` | Processes queued upload parse jobs through the local worker pattern. |
| `monitoring_worker.py` | Processes single-product monitoring imports, normalizes snapshots, runs deterministic/AI recommendation generation, writes recommendations, AI runs, agent events, and audits. |
| `ai_recommendation_brain.py` | Builds DeepSeek prompts, includes agent config, validates strict JSON, applies safety boundaries, and falls back when configured. |
| `account_agent_workflow.py` | Legacy deterministic account-import workflow helper for `run-analysis` and old Agent Control Center cards. This is a bridge kept for compatibility while LangGraph owns upload-created workflows. |
| `workflow_queue.py` | Local background-task adapter for account-import LangGraph runs. It is structured so Celery can replace the local adapter later. |
| `account_import_builder.py` | Shared account-import creation service used by both processed-upload import creation and the multipart report endpoint. |
| `deepseek_client.py` | Existing DeepSeek JSON client abstraction with retries and configuration errors when API key is missing. |

## Database Tables That Already Exist
| Table | Current role |
| --- | --- |
| `uploads`, `upload_parse_runs`, `upload_parsed_rows`, `upload_parse_errors` | Upload and parse state. |
| `account_imports`, `account_import_entities`, `product_mapping_suggestions` | Account-level report import, grouping, and product mapping suggestions. |
| `monitoring_imports`, `monitoring_snapshots`, `recommendations`, `recommendation_decisions`, `ai_runs` | Single-product monitoring, recommendation, approval, and AI run records. |
| `agent_definitions`, `agent_configs`, `agent_workflows`, `agent_workflow_edges`, `agent_run_events`, `agent_control_actions` | Agent Control Center support. `agent_workflows` now stores durable graph state for account-import analysis while legacy edge/event tables remain for old views. |
| `agent_workflow_checkpoints`, `agent_workflow_events`, `agent_tool_calls`, `agent_llm_calls`, `human_approval_gates` | LangGraph orchestration state, trace, future scoped tool calls, LLM calls, and approval gates. |
| `audit_logs` | Audit trail for uploads, decisions, agent controls, and workflow-adjacent actions. |

## What Currently Works
- Account-level report upload from the Agent Control Center performs a real multipart upload, object storage, local parse processing, account import creation, report detection, entity grouping, mapping suggestion creation, and workflow scheduling.
- Agent Control Center Upload Report now uses `POST /v1/workspaces/{workspace_id}/uploads/report`, sends multipart file bytes, creates an upload/import/workflow, and returns a `workflow_id`.
- Upload-created account imports run through the LangGraph-compatible workflow runner and persist workflow checkpoints, workflow events, LLM call metadata, recommendations, and human approval gates.
- Run Analysis on a selected account import calls a real backend endpoint and creates deterministic account-level agent runs plus approval-only recommendations.
- Single-product monitoring worker can process queued monitoring imports and create recommendations.
- DeepSeek recommendation brain exists behind a provider abstraction and validates JSON output before saving recommendations.
- Deterministic fallback exists for monitoring recommendations.
- Agent config fields are persisted and exposed through API/UI.
- Agent run controls are audited and visible.
- Recommendation approve/reject endpoints require notes and do not execute live Amazon Ads changes.
- Frontend unit/API tests, backend tests, and Playwright smoke tests currently pass.

## Mock-Only Or Bridge Implementations
- The legacy `run-analysis` account flow is still a deterministic helper that writes `ai_runs`; it has not been fully replaced by LangGraph in the old Agent Control Center endpoint.
- Workflow graph endpoints synthesize nodes/edges from `ai_runs`, config, and events rather than loading graph checkpoints.
- Agent Templates are config presets, not a plugin/marketplace system.
- `agent_tool_calls` exists but is reserved for future scoped internal tool tracing.
- No Redis/Celery queue is configured. Existing local job repositories/workers plus FastAPI background tasks are the current queue abstraction.

## Buttons And UI Wiring Status
| UI action | Current status |
| --- | --- |
| Agent Control Center Upload Report | Wired to the multipart report endpoint. Button is disabled until a file is selected, shows progress/success/error, returns import/workflow IDs, and refreshes workflow data. |
| Agent Control Center Run Analysis | Wired for account import analysis and monitoring import analysis. Shows visible message if no import is selected. |
| Pause/Resume/Stop/Rerun all | Calls agent-run control endpoints when eligible runs exist; otherwise shows visible operator feedback. |
| Configure agents | Refreshes config; inspector edits persist through `PATCH /agent-configs/{agent_id}`. |
| View approvals | Scrolls to approval checkpoints. Dedicated approvals route is not implemented yet. |
| Approval cards approve/reject | Calls recommendation decision endpoints. The unimplemented Edit button was removed. |
| Product upload init/confirm | Wired; local worker errors now surface visibly. |
| Column mapping/scoring/campaign/export controls | Wired to backend routes; guarded actions now show messages instead of silent returns. |

## Main Refactor Targets
1. Add LangGraph dependency and orchestration package structure without breaking existing routes.
2. Replace bridge account workflow execution with LangGraph nodes.
3. Persist workflow state, checkpoints, events, tool calls, LLM calls, and human approval gates in Postgres.
4. Introduce workflow-level APIs for status, events, recommendations, pause, resume, stop, and rerun.
5. Add a one-shot multipart report upload endpoint that creates upload/import/workflow records and enqueues execution.
6. Keep the existing local worker pattern first, then make the queue abstraction Celery-ready.
7. Ensure DeepSeek prompt generation receives graph state and agent config while keeping secrets backend-only.
8. Enforce AI output validation and store rejected recommendations per workflow.

## Must Not Be Broken
- Existing upload init/object/confirm APIs.
- Existing account import creation and entity grouping.
- Existing product upload, column mapping, scoring, campaign plan, and bulk export workflows.
- Existing single-product monitoring worker and recommendation approval flow.
- Existing Agent Control Center routes and config endpoints.
- Workspace isolation and role checks.
- Approval boundary: no agent may approve/reject recommendations or mutate live Amazon Ads.
- Existing tests and local fake storage behavior.

## Recommended Next Step
Start Phase A with the smallest durable workflow foundation:

1. Add the LangGraph dependency and `apps/api/app/orchestration/` package.
2. Add JSON-serializable `AdsWorkflowState`.
3. Add workflow/checkpoint/event/tool/LLM/approval-gate migration, preserving existing tables.
4. Add repository methods for workflow state/events.
5. Add a minimal graph with `start`, `report_detection`, `metrics_analysis`, and `finalize` nodes.
6. Add API status/event endpoints for workflow records.
7. Keep current account upload APIs working while returning `workflow_id` where possible.

## Phase A Implementation Notes

Implemented in this slice:

- LangGraph was added to API project dependencies.
- `apps/api/app/orchestration/` now contains workflow state, nodes, routing, checkpoint/event helpers, validation, and a LangGraph-compatible runner with local fallback.
- `agent_workflows` is extended by migration instead of replaced.
- New durable tables were added for workflow checkpoints, workflow events, future tool calls, future LLM calls, and human approval gates.
- Creating an account import now creates a workflow record, schedules the local graph path through the workflow queue adapter, and returns `workflow_id`.
- The Agent Control Center upload path now uses a one-shot multipart endpoint, stores bytes, processes the local upload job, creates the account import, creates the workflow, and schedules the graph run.
- Workflow status, event timeline, pause, resume, stop, and rerun endpoints are available under `/v1/workspaces/{workspace_id}/workflows/{workflow_id}`.
- Safety boundaries remain explicit: recommendation only, human approval required, no live Amazon Ads change executed.

Still pending:

- Replace the legacy `run-analysis` account flow with the LangGraph workflow view.
- Move upload parsing itself behind a real Celery worker in deployed queue mode.
- Add first-class UI polling against `/workflows/{workflow_id}` rather than only legacy account-import workflow views.
- Add LLM/tool call persistence around DeepSeek and internal scoped tools.
