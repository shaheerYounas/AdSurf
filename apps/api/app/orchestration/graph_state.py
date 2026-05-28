from datetime import UTC, datetime
from typing import Any, TypedDict


class AdsWorkflowState(TypedDict, total=False):
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
    product_mappings: list[dict[str, Any]]
    grouped_entities: dict[str, Any]
    metrics_rollups: dict[str, Any]
    agent_config: dict[str, Any]
    recommendations: list[dict[str, Any]]
    rejected_recommendations: list[dict[str, Any]]
    dashboard_summary: dict[str, Any]
    human_approval_required: bool
    current_node: str
    status: str
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    trace_ids: list[str]
    safety_boundaries: dict[str, Any]
    created_at: str
    updated_at: str


def initial_state(
    *,
    workflow_id: str,
    workspace_id: str,
    account_import_id: str | None = None,
    upload_id: str | None = None,
    product_id: str | None = None,
    agent_config: dict | None = None,
) -> AdsWorkflowState:
    now = datetime.now(UTC).isoformat()
    return {
        "workflow_id": workflow_id,
        "workspace_id": workspace_id,
        "account_import_id": account_import_id,
        "upload_id": upload_id,
        "product_id": product_id,
        "report_type": None,
        "detected_report_type": None,
        "detection_confidence": None,
        "rows_count": 0,
        "parsed_rows_ref": None,
        "product_mappings": [],
        "grouped_entities": {},
        "metrics_rollups": {},
        "agent_config": agent_config or {},
        "recommendations": [],
        "rejected_recommendations": [],
        "dashboard_summary": {},
        "human_approval_required": True,
        "current_node": "start_workflow",
        "status": "pending",
        "errors": [],
        "warnings": [],
        "trace_ids": [],
        "safety_boundaries": {
            "may_generate_recommendation_decisions": True,
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
            "amazon_ads_api_mutation_allowed": False,
        },
        "created_at": now,
        "updated_at": now,
    }


def touch_state(state: AdsWorkflowState, *, node_name: str, status: str | None = None) -> AdsWorkflowState:
    updated = dict(state)
    updated["current_node"] = node_name
    if status:
        updated["status"] = status
    updated["updated_at"] = datetime.now(UTC).isoformat()
    return updated
