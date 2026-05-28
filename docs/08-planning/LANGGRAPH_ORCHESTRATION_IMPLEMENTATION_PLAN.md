# LangGraph Orchestration Implementation Plan

## Goal
Upgrade AdSurf's backend from custom/manual agent flow into a production-ready multi-agent orchestration backend using FastAPI, LangGraph, Postgres state, Redis/Celery or the existing worker pattern, DeepSeek AI provider, and tracing/audit logs.

AdSurf is an Amazon Ads AI recommendation control center. Users upload Amazon Ads reports or bulk sheets. The app detects report type, resolves products/ASINs/SKUs, calculates metrics, runs AI agents, creates recommendations, and sends them to human approval.

Agents must never directly mutate live Amazon Ads accounts. Agents may create recommendation records only. Humans approve or reject recommendations.

## Best-Fit Backend Architecture
- Frontend: existing Next.js app.
- Backend API: existing FastAPI app.
- Agent orchestration: LangGraph.
- LLM provider: existing DeepSeek client/provider abstraction.
- Database/state: Postgres/Supabase.
- Queue: Redis + Celery, or existing worker pattern if Redis is not configured yet.
- File storage: existing fake/Supabase storage.
- Tracing: Postgres trace tables first, OpenTelemetry-compatible structure later.
- Human approval: existing approval/recommendation decision flow.

Do not rewrite the whole backend. Refactor in phases. Keep existing APIs working while introducing LangGraph orchestration.

## Current Problem
The app currently has agents, agent configs, agent runs, monitoring worker, DeepSeek recommendation brain, and UI control center, but the flow is still partly custom/manual. Some buttons and flows may be visually present but not fully connected. We need a real durable workflow backend where every agent step is a graph node with state, events, retry/failure handling, and human approval gates.

## Main Principle
AdSurf should treat agents like a workflow system, not like a chatbot.

## Required Backend Flow
1. User uploads report.
2. FastAPI creates account_import / upload record.
3. Celery/background worker starts LangGraph workflow.
4. LangGraph node: report detection.
5. LangGraph node: product resolution.
6. LangGraph node: metrics calculation.
7. LangGraph node: AI recommendation brain using DeepSeek.
8. LangGraph specialist review agents:
   - bid optimization
   - negative keyword
   - budget allocation
   - pause review
9. LangGraph node: stakeholder reporting.
10. LangGraph node: human approval checkpoint.
11. Recommendations become pending approval.
12. User approves/rejects in UI.
13. Audit logs are saved.
14. No live Amazon Ads mutation happens.

## Phase 1 - Audit Current Backend First
Inspect:
- `apps/api/app/api/v1/agents.py`
- `apps/api/app/api/v1/uploads.py`
- `apps/api/app/api/v1/monitoring.py`
- `apps/api/app/services/monitoring_worker.py`
- `apps/api/app/services/monitoring_agents.py`
- `apps/api/app/services/ai_recommendation_brain.py`
- `apps/api/app/services/deepseek_client.py`
- `apps/api/app/repositories/agent_control.py`
- `apps/api/app/repositories/monitoring.py`
- `apps/api/app/schemas/agent_control.py`
- `apps/api/app/schemas/monitoring.py`
- `supabase/migrations/*`
- frontend upload/agent components

Create:
- `docs/09-testing/BACKEND_ORCHESTRATION_AUDIT.md`

Include:
- what currently works
- what is mock-only
- what buttons are not wired
- what backend endpoints exist
- what database tables exist
- what must be refactored
- what must not be broken

## Phase 2 - Add LangGraph Dependency And Structure
Add LangGraph to the API project dependencies.

Create folder:
- `apps/api/app/orchestration/`

Add files:
- `__init__.py`
- `graph_state.py`
- `ads_workflow_graph.py`
- `nodes.py`
- `router.py`
- `checkpoints.py`
- `events.py`
- `validation.py`

Purposes:
- `graph_state.py`: typed workflow state.
- `ads_workflow_graph.py`: LangGraph workflow builder.
- `nodes.py`: individual agent nodes.
- `router.py`: conditional routing and failure/human approval gates.
- `checkpoints.py`: persist state/checkpoints to Postgres.
- `events.py`: write agent events/traces.
- `validation.py`: validate AI output and workflow safety.

## Phase 3 - Define Workflow State
Create a JSON-serializable typed state object:

```python
class AdsWorkflowState(TypedDict):
    workflow_id: str
    workspace_id: str
    account_import_id: str | None
    upload_id: str | None
    product_id: str | None
    report_type: str | None
    detected_report_type: str | None
    detection_confidence: str | None
    rows_count: int
    parsed_rows_ref: str | None
    product_mappings: list[dict]
    grouped_entities: dict
    metrics_rollups: dict
    agent_config: dict
    recommendations: list[dict]
    rejected_recommendations: list[dict]
    dashboard_summary: dict
    human_approval_required: bool
    current_node: str
    status: str
    errors: list[dict]
    warnings: list[dict]
    trace_ids: list[str]
    created_at: str
    updated_at: str
```

## Phase 4 - Database Tables For Workflows, Checkpoints, And Traces
Add Supabase/Postgres migration for:
- `agent_workflows`
- `agent_workflow_checkpoints`
- `agent_workflow_events`
- `agent_tool_calls`
- `agent_llm_calls`
- `human_approval_gates`

All tables must be workspace-scoped and auditable.

## Phase 5 - Build LangGraph Nodes
Implement:
1. `start_workflow_node`
2. `report_detection_node`
3. `product_resolution_node`
4. `metrics_analysis_node`
5. `ai_recommendation_brain_node`
6. `bid_optimization_agent_node`
7. `negative_keyword_agent_node`
8. `budget_allocation_agent_node`
9. `pause_review_agent_node`
10. `stakeholder_reporting_agent_node`
11. `human_approval_gate_node`
12. `finalize_workflow_node`
13. `failure_node`

## Phase 6 - Routing Rules
Default route:

`start -> report_detection -> product_resolution -> metrics_analysis -> ai_recommendation_brain -> specialist agents -> stakeholder_reporting -> human_approval_gate -> finalize`

Conditional routes:
- missing required columns -> human/data quality gate
- product mapping needed -> waiting for human
- DeepSeek fails and mode is deepseek -> failure node
- DeepSeek fails and mode is hybrid/fallback -> deterministic fallback
- user stopped workflow -> stopped
- user paused workflow -> paused
- recommendations require approval -> human approval gate

## Phase 7 - Integrate With Existing Worker
Update monitoring/account import worker so it starts the LangGraph workflow.

API request should:
- create upload/import/workflow record
- enqueue background task
- return workflow_id to frontend

Worker should:
- load workflow
- run LangGraph
- save checkpoints/events
- update status

If Redis/Celery is already available, use it. If not, preserve the existing local worker pattern and structure code so Celery can be added later.

Environment variables:
- `AGENT_ORCHESTRATOR=langgraph`
- `QUEUE_BACKEND=local | celery`
- `REDIS_URL=`
- `LANGGRAPH_CHECKPOINT_BACKEND=postgres`
- `AI_RECOMMENDATION_MODE=deepseek | hybrid | deterministic_fallback`

## Phase 8 - API Endpoints
Add/adjust:
- `POST /v1/workspaces/{workspace_id}/account-imports`
- `POST /v1/workspaces/{workspace_id}/uploads/report`
- `GET /v1/workspaces/{workspace_id}/workflows/{workflow_id}`
- `GET /v1/workspaces/{workspace_id}/workflows/{workflow_id}/events`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/pause`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/resume`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/stop`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/rerun`
- `GET /v1/workspaces/{workspace_id}/workflows/{workflow_id}/recommendations`
- `GET /v1/workspaces/{workspace_id}/approval-gates`
- `POST /v1/workspaces/{workspace_id}/approval-gates/{gate_id}/approve`
- `POST /v1/workspaces/{workspace_id}/approval-gates/{gate_id}/reject`

Existing agent endpoints should continue working.

## Phase 9 - Fix Upload Button Flow
Frontend:
- file input stores selected file
- upload button enabled only when file selected
- clicking upload sends multipart/form-data
- shows loading state
- shows success message with upload/import/workflow ID
- shows error message if backend fails
- after success, polls workflow status
- workflow canvas updates current node

Backend:
- accepts multipart file
- stores file
- creates upload/import
- creates workflow
- enqueues LangGraph run
- returns IDs

Acceptance: selecting a report and clicking Upload Report must never silently do nothing.

## Phase 10 - Deep Agent Configuration
Agent configs must persist, display, influence LangGraph state, influence DeepSeek prompt, and influence backend validation. API keys must not be exposed to frontend.

## Phase 11 - AI Output Validation
Validate:
- allowed recommendation type
- entity exists in grouped metrics
- confidence threshold
- bid multipliers
- negative keyword thresholds
- pause confidence requirements
- `approval_required` true
- `executes_live_amazon_change` false
- no claims of live Amazon Ads mutation
- evidence present
- reasoning summary present

Invalid AI recommendations should be rejected individually and stored in `rejected_recommendations`.

## Phase 12 - Observability And Tracing
Every node writes events:
- workflow started
- node started/completed/failed
- LLM call started/completed/failed
- tool call started/completed/failed
- fallback used
- recommendation validated/rejected
- human approval waiting
- user approved/rejected
- workflow completed

Use Postgres first and structure for OpenTelemetry later.

## Phase 13 - Tool Layer
Use scoped internal tools only:
- read uploaded report
- query parsed rows
- query product profiles
- query metrics
- create recommendation
- create approval gate
- write audit event

Do not add broad MCP access yet. Agents should not receive database credentials or unscoped tools.

## Phase 14 - Human Approval And Safety
Hard guardrails:
- agents cannot approve recommendations
- agents cannot reject recommendations
- agents cannot call Amazon Ads mutation APIs
- agents cannot execute bid changes
- agents cannot pause campaigns
- agents cannot add negative keywords live
- agents cannot bypass approval gates

Every recommendation must include:
- `recommendation_only: true`
- `requires_human_approval: true`
- `executes_live_amazon_change: false`

## Phase 15 - Testing
Backend unit tests:
- LangGraph state serialization
- report detection node
- product resolution node
- metrics analysis node
- AI recommendation brain node with mocked DeepSeek
- invalid AI output validation
- fallback routing
- human approval gate node
- workflow pause/stop/rerun state
- event tracing

Backend integration tests:
- upload file creates workflow
- workflow happy path
- missing columns route to data quality gate
- DeepSeek failure routes to fallback
- recommendations saved
- approval gate created
- approve/reject updates audit only

Frontend E2E tests:
- user uploads report
- workflow ID appears
- workflow canvas updates
- trace timeline appears
- recommendations appear
- approval queue works

## Phase 16 - Documentation
Create/update:
- `docs/03-architecture/AGENT_ORCHESTRATION_BACKEND.md`
- `docs/04-ai-agents/LANGGRAPH_WORKFLOW.md`
- `docs/05-workflows/ACCOUNT_BULK_REPORT_WORKFLOW.md`
- `docs/09-testing/FUNCTIONALITY_AUDIT.md`
- `docs/09-testing/MANUAL_QA_CHECKLIST.md`
- `docs/06-ui-ux/USER_GUIDE.md`

## Implementation Priority
Phase A:
- Fix upload button and create real workflow records.
- Add workflow/event tables.
- Add basic LangGraph workflow with start/report_detection/metrics/finalize.

Phase B:
- Move existing monitoring/AI recommendation logic into LangGraph nodes.
- Add checkpoints/events.
- Show workflow status in UI.

Phase C:
- Add full agent configs to state and DeepSeek prompt.
- Add validation/fallback routing.

Phase D:
- Add advanced tracing, approval gates, tests, and docs.

Do not implement Temporal yet. Do not add MCP yet. Design the backend so Temporal/MCP can be added later.

## Acceptance Criteria
- Upload Report performs a real backend upload.
- A `workflow_id` is created.
- LangGraph workflow runs in background.
- Workflow status/events can be viewed from API/UI.
- Agents run as graph nodes.
- DeepSeek AI generates recommendations through a graph node.
- Backend validates AI output.
- Recommendations require human approval.
- No live Amazon Ads mutation is possible.
- Pause/resume/stop/rerun works at workflow level.
- Every step is traceable.
- Tests cover happy paths and failure paths.
- Docs explain the new backend clearly.

## Progress Log

### 2026-05-28 Phase A Foundation
- Added LangGraph as an API dependency.
- Added `apps/api/app/orchestration/` with graph state, graph runner, nodes, routing, checkpoints, events, and validation.
- Added durable workflow/checkpoint/event/tool-call/LLM-call/human-approval-gate migration.
- Added workflow repository and API endpoints for status, events, pause, resume, stop, and rerun.
- Account import creation now creates a workflow, runs the local graph path, and returns `workflow_id`.
- Safety boundary remains recommendation-only with human approval required and no live Amazon Ads mutation.
