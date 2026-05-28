from uuid import UUID

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, PRODUCT_PROFILE_WRITE_ROLES, WorkspacePrincipal, WorkspaceRole, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.orchestration.ads_workflow_graph import AdsWorkflowRunner
from apps.api.app.repositories.account_imports import AccountImportRepository, get_account_import_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.workflows import WorkflowRepository, get_workflow_repository, new_workflow_event
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.workflows import WorkflowControlRequest, WorkflowStatus, WorkflowSummaryResponse

router = APIRouter()
APPROVAL_GATE_DECISION_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.APPROVER}


@router.get("/workspaces/{workspace_id}/workflows/{workflow_id}")
def get_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    workflow = _require_workflow(workspace_id=workspace_id, workflow_id=workflow_id, repository=workflow_repository)
    events = workflow_repository.list_events(workspace_id=workspace_id, workflow_id=workflow_id)[-10:]
    response = WorkflowSummaryResponse(workflow=workflow, progress=_progress(workflow.state_json), latest_events=events)
    return success_response(data=response.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/workflows/{workflow_id}/events")
def list_workflow_events(
    workspace_id: UUID,
    workflow_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_workflow(workspace_id=workspace_id, workflow_id=workflow_id, repository=workflow_repository)
    events = workflow_repository.list_events(workspace_id=workspace_id, workflow_id=workflow_id)
    return success_response(data=[event.model_dump(mode="json") for event in events], meta={"total": len(events)})


@router.get("/workspaces/{workspace_id}/approval-gates")
def list_approval_gates(
    workspace_id: UUID,
    status: str | None = Query(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    gates = workflow_repository.list_human_approval_gates(workspace_id=workspace_id, status=status)
    return success_response(data=[_json_safe(gate) for gate in gates], meta={"total": len(gates), "secrets_exposed": False})


@router.post("/workspaces/{workspace_id}/approval-gates/{gate_id}/approve")
def approve_approval_gate(
    workspace_id: UUID,
    gate_id: UUID,
    payload: WorkflowControlRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    return _decide_approval_gate(workspace_id=workspace_id, gate_id=gate_id, status="approved", payload=payload, principal=principal, workflow_repository=workflow_repository, audit_repository=audit_repository)


@router.post("/workspaces/{workspace_id}/approval-gates/{gate_id}/reject")
def reject_approval_gate(
    workspace_id: UUID,
    gate_id: UUID,
    payload: WorkflowControlRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    return _decide_approval_gate(workspace_id=workspace_id, gate_id=gate_id, status="rejected", payload=payload, principal=principal, workflow_repository=workflow_repository, audit_repository=audit_repository)


@router.post("/workspaces/{workspace_id}/workflows/{workflow_id}/pause")
def pause_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    payload: WorkflowControlRequest | None = None,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    return _control_workflow(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        principal=principal,
        workflow_repository=workflow_repository,
        audit_repository=audit_repository,
        status=WorkflowStatus.PAUSED,
        action="workflow.paused",
        event_type="agent_paused",
        message="Workflow paused by user.",
        reason=(payload.reason if payload else "User requested pause."),
    )


@router.post("/workspaces/{workspace_id}/workflows/{workflow_id}/resume")
def resume_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    payload: WorkflowControlRequest | None = None,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    workflow = _require_workflow(workspace_id=workspace_id, workflow_id=workflow_id, repository=workflow_repository)
    if workflow.account_import_id is None:
        raise ApiError(code="WORKFLOW_NOT_RESUMABLE", message="Only account import workflows can be resumed right now.", status_code=409)
    updated = workflow_repository.update_workflow(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        status=WorkflowStatus.RUNNING,
        current_node=workflow.current_node or "start_workflow",
    )
    workflow_repository.insert_event(
        event=new_workflow_event(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            node_name=workflow.current_node or "resume",
            event_type="agent_resumed",
            message="Workflow resumed by user.",
            metadata_json={"reason": payload.reason if payload else "User requested resume.", "executes_live_amazon_change": False},
        )
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="workflow.resumed",
        entity_type="agent_workflow",
        entity_id=workflow_id,
        details={"reason": payload.reason if payload else "User requested resume.", "execution_boundary": "recommendation_only_no_live_amazon_change"},
    )
    final_state = AdsWorkflowRunner(
        workflow_repository=workflow_repository,
        account_import_repository=account_import_repository,
        monitoring_repository=monitoring_repository,
    ).run_account_import_workflow(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        account_import_id=workflow.account_import_id,
        upload_id=workflow.upload_id,
        agent_config=workflow.state_json.get("agent_config", {}),
    )
    refreshed = workflow_repository.get_workflow(workspace_id=workspace_id, workflow_id=workflow_id) or updated
    return success_response(data={"workflow": refreshed.model_dump(mode="json"), "state": final_state})


@router.post("/workspaces/{workspace_id}/workflows/{workflow_id}/stop")
def stop_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    payload: WorkflowControlRequest | None = None,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    return _control_workflow(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        principal=principal,
        workflow_repository=workflow_repository,
        audit_repository=audit_repository,
        status=WorkflowStatus.STOPPED,
        action="workflow.stopped",
        event_type="agent_stopped",
        message="Workflow stopped by user. No live Amazon Ads change executed.",
        reason=(payload.reason if payload else "User requested stop."),
    )


@router.post("/workspaces/{workspace_id}/workflows/{workflow_id}/rerun")
def rerun_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    payload: WorkflowControlRequest | None = None,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    workflow = _require_workflow(workspace_id=workspace_id, workflow_id=workflow_id, repository=workflow_repository)
    if workflow.account_import_id is None:
        raise ApiError(code="WORKFLOW_NOT_RERUNNABLE", message="Only account import workflows can be rerun right now.", status_code=409)
    workflow_repository.insert_event(
        event=new_workflow_event(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            node_name="rerun",
            event_type="agent_rerun",
            message="Workflow rerun requested by user.",
            metadata_json={"reason": payload.reason if payload else "User requested rerun.", "executes_live_amazon_change": False},
        )
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="workflow.rerun_requested",
        entity_type="agent_workflow",
        entity_id=workflow_id,
        details={"reason": payload.reason if payload else "User requested rerun.", "execution_boundary": "recommendation_only_no_live_amazon_change"},
    )
    final_state = AdsWorkflowRunner(
        workflow_repository=workflow_repository,
        account_import_repository=account_import_repository,
        monitoring_repository=monitoring_repository,
    ).run_account_import_workflow(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        account_import_id=workflow.account_import_id,
        upload_id=workflow.upload_id,
        agent_config=workflow.state_json.get("agent_config", {}),
    )
    refreshed = _require_workflow(workspace_id=workspace_id, workflow_id=workflow_id, repository=workflow_repository)
    return success_response(data={"workflow": refreshed.model_dump(mode="json"), "state": final_state})


def _control_workflow(
    *,
    workspace_id: UUID,
    workflow_id: UUID,
    principal: WorkspacePrincipal,
    workflow_repository: WorkflowRepository,
    audit_repository: AuditLogRepository,
    status: WorkflowStatus,
    action: str,
    event_type: str,
    message: str,
    reason: str,
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    workflow = _require_workflow(workspace_id=workspace_id, workflow_id=workflow_id, repository=workflow_repository)
    updated = workflow_repository.update_workflow(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        status=status,
        current_node=workflow.current_node,
        state_json={**workflow.state_json, "status": status.value, "control_reason": reason},
    )
    workflow_repository.insert_event(
        event=new_workflow_event(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            node_name=workflow.current_node or "control",
            event_type=event_type,
            message=message,
            metadata_json={"reason": reason, "executes_live_amazon_change": False},
        )
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action=action,
        entity_type="agent_workflow",
        entity_id=workflow_id,
        details={"reason": reason, "execution_boundary": "recommendation_only_no_live_amazon_change"},
    )
    return success_response(data=updated.model_dump(mode="json") if updated else workflow.model_dump(mode="json"))


def _decide_approval_gate(*, workspace_id: UUID, gate_id: UUID, status: str, payload: WorkflowControlRequest, principal: WorkspacePrincipal, workflow_repository: WorkflowRepository, audit_repository: AuditLogRepository) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(APPROVAL_GATE_DECISION_ROLES)
    gate = workflow_repository.decide_human_approval_gate(
        workspace_id=workspace_id,
        gate_id=gate_id,
        status=status,
        approver_user_id=principal.user_id,
        decision_note=payload.reason,
    )
    if gate is None:
        raise ApiError(code="APPROVAL_GATE_NOT_FOUND", message="Approval gate was not found or already decided.", status_code=404)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action=f"approval_gate.{status}",
        entity_type="human_approval_gate",
        entity_id=gate_id,
        details={"decision_note": payload.reason, "executes_live_amazon_change": False},
    )
    workflow_repository.insert_event(
        event=new_workflow_event(
            workflow_id=gate["workflow_id"],
            workspace_id=workspace_id,
            node_name="human_approval_gate",
            event_type="user_approved" if status == "approved" else "user_rejected",
            message=f"Human {status} approval gate. No live Amazon Ads change executed.",
            metadata_json={"gate_id": str(gate_id), "decision_note": payload.reason, "executes_live_amazon_change": False},
        )
    )
    return success_response(data=_json_safe(gate))


def _require_workflow(*, workspace_id: UUID, workflow_id: UUID, repository: WorkflowRepository):
    workflow = repository.get_workflow(workspace_id=workspace_id, workflow_id=workflow_id)
    if workflow is None:
        raise ApiError(code="WORKFLOW_NOT_FOUND", message="Agent workflow was not found.", status_code=404)
    return workflow


def _progress(state: dict) -> dict:
    order = [
        "start_workflow",
        "report_detection",
        "product_resolution",
        "metrics_analysis",
        "ai_recommendation_brain",
        "bid_optimization",
        "negative_keyword",
        "budget_allocation",
        "pause_review",
        "stakeholder_reporting",
        "human_approval_gate",
    ]
    current = state.get("current_node") or "start_workflow"
    try:
        index = order.index(current)
    except ValueError:
        index = 0
    return {"current_node": current, "completed_steps": index, "total_steps": len(order), "percent": round((index / max(len(order) - 1, 1)) * 100)}


def _json_safe(item: dict) -> dict:
    return {key: str(value) if isinstance(value, UUID) else value for key, value in item.items()}
