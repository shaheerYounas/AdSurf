# LangGraph Workflow

AdSurf treats agents as an approval-controlled workflow system, not as a chatbot. Account-level report analysis now has a LangGraph-compatible graph with durable workflow state and trace events.

## Current Node Order

1. `start_workflow`
2. `report_detection`
3. `product_resolution`
4. `metrics_analysis`
5. `ai_recommendation_brain`
6. `bid_optimization`
7. `negative_keyword`
8. `budget_allocation`
9. `pause_review`
10. `stakeholder_reporting`
11. `human_approval_gate`

The human approval gate is terminal for now. It leaves the workflow in `waiting_for_human` and does not execute live Amazon Ads changes.

## State Shape

Workflow state is JSON-serializable and includes:

- workspace, upload, account import, and product IDs
- detected report type and confidence
- grouped entities and metric rollups
- agent configuration
- valid and rejected recommendations
- dashboard summary
- warnings and errors
- safety boundaries

## Routing

Current routing:

- missing required report columns route to the human/data-quality gate
- node failures route to `failure`
- successful analysis routes to `human_approval_gate`

Future routing will add DeepSeek failure fallback, pause/stop checks inside long-running workers, and per-product/per-campaign chunking.

## Trace Events

Each node writes events to `agent_workflow_events`:

- `node_started`
- `node_completed`
- `node_failed`
- `workflow_completed`

The schema is OpenTelemetry-friendly: it stores workflow, node, agent, provider/model, latency, metadata, and timestamp.

## AI Boundary

The current first slice uses deterministic recommendation generation in the graph node while preserving the DeepSeek handoff shape for the next phase. Before saving or surfacing recommendations, backend validation requires:

- human approval
- no live Amazon Ads mutation
- evidence
- reasoning summary
- allowed recommendation type
- confidence threshold
- bid multiplier limits

Invalid recommendations are rejected individually and kept in `rejected_recommendations`.
