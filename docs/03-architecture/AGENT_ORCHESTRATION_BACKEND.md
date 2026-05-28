# Agent Orchestration Backend

AdSurf now has a durable workflow foundation for account-level Amazon Ads report analysis. The first implementation slice keeps the existing FastAPI APIs working while introducing a LangGraph-compatible orchestration layer backed by Postgres/Supabase workflow state, checkpoints, and trace events.

## Architecture

- FastAPI remains the public backend API.
- LangGraph is the target graph runner for agent orchestration.
- A local fallback runner executes the same node sequence when LangGraph is not installed in a local or test environment.
- Postgres/Supabase stores workflow records, checkpoints, trace events, future tool calls, future LLM calls, and human approval gates.
- Existing account import, report detection, product resolution, and deterministic recommendation services remain the source of truth for MVP behavior.

## Durable State

The `agent_workflows` table is extended with:

- `account_import_id`
- `upload_id`
- `workflow_type`
- `current_node`
- `state_json`
- `error_json`
- `created_by`
- `completed_at`

New tables:

- `agent_workflow_checkpoints`
- `agent_workflow_events`
- `agent_tool_calls`
- `agent_llm_calls`
- `human_approval_gates`

All workflow-adjacent tables are workspace-scoped or resolve workspace access through `agent_workflows`.

## Safety Boundary

Agent workflows may create analysis state and recommendation evidence only.

They must not:

- approve recommendations
- reject recommendations
- execute Amazon Ads API mutations
- change bids
- pause campaigns
- add negative keywords live
- bypass approval gates

Every workflow state includes:

```json
{
  "recommendation_only": true,
  "requires_human_approval": true,
  "executes_live_amazon_change": false
}
```

## API Surface

Current workflow endpoints:

- `GET /v1/workspaces/{workspace_id}/workflows/{workflow_id}`
- `GET /v1/workspaces/{workspace_id}/workflows/{workflow_id}/events`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/pause`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/resume`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/stop`
- `POST /v1/workspaces/{workspace_id}/workflows/{workflow_id}/rerun`

Creating an account import now creates a workflow record and returns `workflow_id`.

## Local Execution

For MVP local development, account import workflow execution runs immediately through the graph runner. If LangGraph is unavailable, AdSurf uses the local fallback sequence with the same node functions and trace persistence.

Future queue execution should use:

- `AGENT_ORCHESTRATOR=langgraph`
- `QUEUE_BACKEND=local | celery`
- `REDIS_URL=`
- `LANGGRAPH_CHECKPOINT_BACKEND=postgres`
- `AI_RECOMMENDATION_MODE=deepseek | hybrid | deterministic_fallback`
