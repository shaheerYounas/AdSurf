from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, WorkspacePrincipal, WorkspaceRole, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.account_imports import AccountImportRepository, get_account_import_repository
from apps.api.app.repositories.agent_control import AgentControlRepository, get_agent_control_repository, new_agent_event
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.schemas.agent_control import AgentConfig, AgentConfigPatch, AgentControlRequest, AgentRunDetail, AgentWorkflowEdge, AgentWorkflowNode, AgentWorkflowResponse
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.monitoring import AiRun
from apps.api.app.services.account_agent_workflow import build_account_agent_workflow_runs, build_account_workflow_events
from apps.api.app.services.ai_provider_factory import available_backend_ai_providers
from apps.api.app.services.agent_registry import AGENT_DEFINITION_BY_ID, AGENT_WORKFLOW_ORDER, agent_id_for_run_name, list_agent_definitions

router = APIRouter()

AGENT_CONFIG_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
AGENT_CONTROL_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.ANALYST}

EDGE_SUMMARIES = {
    ("report_upload_node", "report_detection_agent"): ["raw upload metadata", "parsed headers", "sample rows"],
    ("report_detection_agent", "product_resolution_agent"): ["detected report type", "missing columns", "available entity levels"],
    ("product_resolution_agent", "metrics_analysis_agent"): ["product mappings", "ASIN/SKU groups", "campaign/ad group/target entities"],
    ("metrics_analysis_agent", "ai_recommendation_brain_agent"): ["normalized metrics", "campaign rollups", "ad group rollups", "target rollups", "search term rollups", "top winners", "top wasters", "data quality warnings"],
    ("ai_recommendation_brain_agent", "bid_optimization_agent"): ["bid recommendation candidates", "metric evidence", "confidence", "risk notes"],
    ("ai_recommendation_brain_agent", "negative_keyword_agent"): ["negative keyword candidates", "wasted spend evidence", "confidence", "risk notes"],
    ("ai_recommendation_brain_agent", "budget_allocation_agent"): ["budget review candidates", "spend share", "sales share", "risk notes"],
    ("ai_recommendation_brain_agent", "pause_review_agent"): ["pause review candidates", "zero-order spend evidence", "risk notes"],
    ("bid_optimization_agent", "stakeholder_reporting_agent"): ["bid explanations", "risk notes", "approval notes"],
    ("negative_keyword_agent", "stakeholder_reporting_agent"): ["negative keyword recommendations", "wasted spend evidence", "approval notes"],
    ("budget_allocation_agent", "stakeholder_reporting_agent"): ["budget recommendations", "portfolio/campaign pressure", "approval notes"],
    ("pause_review_agent", "stakeholder_reporting_agent"): ["pause review recommendations", "risk notes", "approval notes"],
    ("stakeholder_reporting_agent", "human_approval_agent"): ["executive summary", "approver notes", "recommendation queue"],
}


@router.get("/workspaces/{workspace_id}/agents")
def list_agents(workspace_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    return success_response(data=[agent.model_dump(mode="json") for agent in list_agent_definitions()])


@router.get("/workspaces/{workspace_id}/agent-ai-providers")
def list_agent_ai_providers(workspace_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    return success_response(
        data=available_backend_ai_providers(),
        meta={"secrets_exposed": False, "message": "API keys are read server-side only and are never returned to the frontend."},
    )


@router.get("/workspaces/{workspace_id}/agent-configs")
def list_agent_configs(
    workspace_id: UUID,
    product_id: UUID | None = Query(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: AgentControlRepository = Depends(get_agent_control_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    configs = repository.list_configs(workspace_id=workspace_id, product_id=product_id)
    return success_response(data=[config.model_dump(mode="json") for config in configs])


@router.patch("/workspaces/{workspace_id}/agent-configs/{agent_id}")
def update_agent_config(
    workspace_id: UUID,
    agent_id: str,
    payload: AgentConfigPatch,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: AgentControlRepository = Depends(get_agent_control_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_CONFIG_ROLES)
    _ensure_agent(agent_id)
    current = repository.get_config(workspace_id=workspace_id, product_id=payload.product_id, agent_id=agent_id)
    updates = {key: value for key, value in payload.model_dump(exclude={"reason"}, exclude_none=True).items()}
    updated, old = repository.upsert_config(config=current.model_copy(update={**updates, "updated_by": principal.user_id, "created_by": current.created_by or principal.user_id}))
    repository.record_control_action(
        workspace_id=workspace_id,
        agent_id=agent_id,
        agent_run_id=None,
        monitoring_import_id=None,
        action="configure",
        actor_user_id=principal.user_id,
        reason=payload.reason,
        metadata_json={"old_config": (old or current).model_dump(mode="json"), "new_config": updated.model_dump(mode="json"), "execution_boundary": "no_live_amazon_change"},
    )
    repository.insert_event(event=new_agent_event(workspace_id=workspace_id, agent_id=agent_id, event_type="agent_configured", message=payload.reason, metadata_json={"old_config": (old or current).model_dump(mode="json"), "new_config": updated.model_dump(mode="json")}))
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="agent_config.updated",
        entity_type="agent_config",
        entity_id=uuid4(),
        details={"agent_id": agent_id, "old_config": (old or current).model_dump(mode="json"), "new_config": updated.model_dump(mode="json"), "reason": payload.reason, "execution_boundary": "no_live_amazon_change"},
    )
    return success_response(data=updated.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/agent-runs")
def list_agent_runs(
    workspace_id: UUID,
    product_id: UUID | None = Query(default=None),
    monitoring_import_id: UUID | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    control_repository: AgentControlRepository = Depends(get_agent_control_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    runs = [_run_detail(run, control_repository=control_repository, monitoring_import_id_filter=monitoring_import_id) for run in monitoring_repository.list_ai_runs(workspace_id=workspace_id, product_id=product_id)]
    filtered = [run for run in runs if (monitoring_import_id is None or run.monitoring_import_id == monitoring_import_id) and (agent_id is None or run.agent_id == agent_id)]
    return success_response(data=[run.model_dump(mode="json") for run in filtered])


@router.get("/workspaces/{workspace_id}/agent-runs/{agent_run_id}")
def get_agent_run(
    workspace_id: UUID,
    agent_run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    control_repository: AgentControlRepository = Depends(get_agent_control_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    run = _find_run(workspace_id=workspace_id, agent_run_id=agent_run_id, monitoring_repository=monitoring_repository)
    if run is None:
        raise ApiError(code="AGENT_RUN_NOT_FOUND", message="Agent run was not found.", status_code=404)
    return success_response(data=_run_detail(run, control_repository=control_repository).model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/monitoring/imports/{import_id}/agent-workflow")
def get_agent_workflow(
    workspace_id: UUID,
    import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    control_repository: AgentControlRepository = Depends(get_agent_control_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    import_record = monitoring_repository.get_import(workspace_id=workspace_id, monitoring_import_id=import_id)
    if import_record is None:
        raise ApiError(code="MONITORING_IMPORT_NOT_FOUND", message="Monitoring import was not found.", status_code=404)
    runs = [_run_detail(run, control_repository=control_repository, monitoring_import_id_filter=import_id) for run in monitoring_repository.list_ai_runs(workspace_id=workspace_id, product_id=import_record.product_id)]
    runs = [run for run in runs if run.monitoring_import_id == import_id]
    configs = {config.agent_id: config for config in control_repository.list_configs(workspace_id=workspace_id, product_id=import_record.product_id)}
    nodes = [_workflow_node(agent_id=agent_id, runs=runs, config=configs.get(agent_id) or control_repository.get_config(workspace_id=workspace_id, product_id=import_record.product_id, agent_id=agent_id)) for agent_id in AGENT_WORKFLOW_ORDER]
    events = control_repository.list_events(workspace_id=workspace_id, monitoring_import_id=import_id)
    edges = _workflow_edges(nodes=nodes, events=events)
    return success_response(data=AgentWorkflowResponse(monitoring_import_id=import_id, nodes=nodes, edges=edges, events=events).model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/account-imports/{account_import_id}/run-analysis")
def run_account_import_analysis(
    workspace_id: UUID,
    account_import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    account_repository: AccountImportRepository = Depends(get_account_import_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    control_repository: AgentControlRepository = Depends(get_agent_control_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_CONTROL_ROLES)
    import_record = account_repository.get_import(workspace_id=workspace_id, account_import_id=account_import_id)
    if import_record is None:
        raise ApiError(code="ACCOUNT_IMPORT_NOT_FOUND", message="Account import was not found.", status_code=404)
    entities = account_repository.list_entities(workspace_id=workspace_id, account_import_id=account_import_id)
    if not entities:
        raise ApiError(code="ACCOUNT_IMPORT_HAS_NO_ENTITIES", message="Account import has no grouped entities to analyze.", status_code=409)
    configs = {config.agent_id: config for config in control_repository.list_configs(workspace_id=workspace_id)}
    runs, recommendations = build_account_agent_workflow_runs(workspace_id=workspace_id, import_record=import_record, entities=entities, configs=configs)
    for run in runs:
        monitoring_repository.insert_ai_run(ai_run=run)
    monitoring_repository.insert_recommendations(recommendations=recommendations)
    for event in build_account_workflow_events(workspace_id=workspace_id, account_import_id=account_import_id, runs=runs):
        if event["agent_run_id"]:
            control_repository.insert_event(
                event=new_agent_event(
                    workspace_id=workspace_id,
                    agent_id=event["agent_id"],
                    agent_run_id=UUID(str(event["agent_run_id"])),
                    monitoring_import_id=None,
                    event_type=event["event_type"],
                    message=event["message"],
                    metadata_json=event["metadata_json"],
                )
            )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="account_import.agent_analysis_completed",
        entity_type="account_import",
        entity_id=account_import_id,
        details={"run_count": len(runs), "recommendation_count": len(recommendations), "execution_boundary": "no_live_amazon_change"},
    )
    return success_response(data={"account_import_id": str(account_import_id), "status": "succeeded", "run_count": len(runs), "recommendation_count": len(recommendations), "execution_boundary": "no_live_amazon_change"})


@router.get("/workspaces/{workspace_id}/account-imports/{account_import_id}/agent-workflow")
def get_account_import_agent_workflow(
    workspace_id: UUID,
    account_import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    account_repository: AccountImportRepository = Depends(get_account_import_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    control_repository: AgentControlRepository = Depends(get_agent_control_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    import_record = account_repository.get_import(workspace_id=workspace_id, account_import_id=account_import_id)
    if import_record is None:
        raise ApiError(code="ACCOUNT_IMPORT_NOT_FOUND", message="Account import was not found.", status_code=404)
    runs = [_run_detail(run, control_repository=control_repository, monitoring_import_id_filter=account_import_id) for run in monitoring_repository.list_ai_runs(workspace_id=workspace_id)]
    runs = [run for run in runs if run.monitoring_import_id == account_import_id]
    configs = {config.agent_id: config for config in control_repository.list_configs(workspace_id=workspace_id)}
    nodes = [_workflow_node(agent_id=agent_id, runs=runs, config=configs.get(agent_id) or control_repository.get_config(workspace_id=workspace_id, product_id=None, agent_id=agent_id)) for agent_id in AGENT_WORKFLOW_ORDER]
    raw_runs = [run for run in monitoring_repository.list_ai_runs(workspace_id=workspace_id) if str(run.output_json.get("_agent_control", {}).get("account_import_id")) == str(account_import_id)]
    events = build_account_workflow_events(workspace_id=workspace_id, account_import_id=account_import_id, runs=raw_runs) if raw_runs else control_repository.list_events(workspace_id=workspace_id)
    edges = _workflow_edges(nodes=nodes, events=events)
    return success_response(data=AgentWorkflowResponse(monitoring_import_id=account_import_id, nodes=nodes, edges=edges, events=events).model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/agent-runs/{agent_run_id}/events")
def list_agent_run_events(
    workspace_id: UUID,
    agent_run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: AgentControlRepository = Depends(get_agent_control_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    events = repository.list_events(workspace_id=workspace_id, agent_run_id=agent_run_id)
    return success_response(data=[event.model_dump(mode="json") for event in events])


@router.get("/workspaces/{workspace_id}/agent-runs/{agent_run_id}/recommendations")
def list_agent_run_recommendations(
    workspace_id: UUID,
    agent_run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    run = _find_run(workspace_id=workspace_id, agent_run_id=agent_run_id, monitoring_repository=monitoring_repository)
    if run is None:
        raise ApiError(code="AGENT_RUN_NOT_FOUND", message="Agent run was not found.", status_code=404)
    detail = _run_detail(run, control_repository=get_agent_control_repository())
    recommendations = monitoring_repository.list_recommendations(workspace_id=workspace_id, product_id=run.product_id)
    related = [item for item in recommendations if str(item.id) in set(detail.recommendation_ids) or item.evidence_json.get("ai_run_id") == str(agent_run_id)]
    return success_response(data=[item.model_dump(mode="json") for item in related])


@router.post("/workspaces/{workspace_id}/agent-runs/{agent_run_id}/pause")
def pause_agent_run(workspace_id: UUID, agent_run_id: UUID, payload: AgentControlRequest, principal: WorkspacePrincipal = Depends(require_workspace_member), monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository), control_repository: AgentControlRepository = Depends(get_agent_control_repository), audit_repository: AuditLogRepository = Depends(get_audit_log_repository)) -> dict:
    return _control_agent_run(workspace_id=workspace_id, agent_run_id=agent_run_id, action="pause", event_type="agent_paused", payload=payload, principal=principal, monitoring_repository=monitoring_repository, control_repository=control_repository, audit_repository=audit_repository)


@router.post("/workspaces/{workspace_id}/agent-runs/{agent_run_id}/resume")
def resume_agent_run(workspace_id: UUID, agent_run_id: UUID, payload: AgentControlRequest, principal: WorkspacePrincipal = Depends(require_workspace_member), monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository), control_repository: AgentControlRepository = Depends(get_agent_control_repository), audit_repository: AuditLogRepository = Depends(get_audit_log_repository)) -> dict:
    return _control_agent_run(workspace_id=workspace_id, agent_run_id=agent_run_id, action="resume", event_type="agent_resumed", payload=payload, principal=principal, monitoring_repository=monitoring_repository, control_repository=control_repository, audit_repository=audit_repository)


@router.post("/workspaces/{workspace_id}/agent-runs/{agent_run_id}/stop")
def stop_agent_run(workspace_id: UUID, agent_run_id: UUID, payload: AgentControlRequest, principal: WorkspacePrincipal = Depends(require_workspace_member), monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository), control_repository: AgentControlRepository = Depends(get_agent_control_repository), audit_repository: AuditLogRepository = Depends(get_audit_log_repository)) -> dict:
    return _control_agent_run(workspace_id=workspace_id, agent_run_id=agent_run_id, action="stop", event_type="agent_stopped", payload=payload, principal=principal, monitoring_repository=monitoring_repository, control_repository=control_repository, audit_repository=audit_repository)


@router.post("/workspaces/{workspace_id}/agent-runs/{agent_run_id}/rerun")
def rerun_agent_run(workspace_id: UUID, agent_run_id: UUID, payload: AgentControlRequest, principal: WorkspacePrincipal = Depends(require_workspace_member), monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository), control_repository: AgentControlRepository = Depends(get_agent_control_repository), audit_repository: AuditLogRepository = Depends(get_audit_log_repository)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_CONTROL_ROLES)
    run = _find_run(workspace_id=workspace_id, agent_run_id=agent_run_id, monitoring_repository=monitoring_repository)
    if run is None:
        raise ApiError(code="AGENT_RUN_NOT_FOUND", message="Agent run was not found.", status_code=404)
    old_detail = _run_detail(run, control_repository=control_repository)
    new_run = run.model_copy(update={"id": uuid4(), "status": "queued", "created_at": datetime.now(UTC), "output_json": {**run.output_json, "_rerun_of": str(run.id)}})
    monitoring_repository.insert_ai_run(ai_run=new_run)
    _record_control(workspace_id=workspace_id, agent_id=old_detail.agent_id, agent_run_id=new_run.id, monitoring_import_id=old_detail.monitoring_import_id, action="rerun", event_type="agent_queued", payload=payload, principal=principal, control_repository=control_repository, audit_repository=audit_repository, metadata={"rerun_of": str(run.id)})
    return success_response(data=_run_detail(new_run, control_repository=control_repository).model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/monitoring/imports/{import_id}/rerun-from-agent/{agent_id}")
def rerun_from_agent(workspace_id: UUID, import_id: UUID, agent_id: str, payload: AgentControlRequest, principal: WorkspacePrincipal = Depends(require_workspace_member), monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository), control_repository: AgentControlRepository = Depends(get_agent_control_repository), audit_repository: AuditLogRepository = Depends(get_audit_log_repository)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_CONTROL_ROLES)
    _ensure_agent(agent_id)
    import_record = monitoring_repository.get_import(workspace_id=workspace_id, monitoring_import_id=import_id)
    if import_record is None:
        raise ApiError(code="MONITORING_IMPORT_NOT_FOUND", message="Monitoring import was not found.", status_code=404)
    _record_control(workspace_id=workspace_id, agent_id=agent_id, agent_run_id=None, monitoring_import_id=import_id, action="rerun_from_here", event_type="agent_queued", payload=payload, principal=principal, control_repository=control_repository, audit_repository=audit_repository, metadata={"rerun_from_agent": agent_id})
    return success_response(data={"monitoring_import_id": str(import_id), "agent_id": agent_id, "status": "queued", "execution_boundary": "no_live_amazon_change"})


def _control_agent_run(*, workspace_id: UUID, agent_run_id: UUID, action: str, event_type: str, payload: AgentControlRequest, principal: WorkspacePrincipal, monitoring_repository: MonitoringRepository, control_repository: AgentControlRepository, audit_repository: AuditLogRepository) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_CONTROL_ROLES)
    run = _find_run(workspace_id=workspace_id, agent_run_id=agent_run_id, monitoring_repository=monitoring_repository)
    if run is None:
        raise ApiError(code="AGENT_RUN_NOT_FOUND", message="Agent run was not found.", status_code=404)
    detail = _run_detail(run, control_repository=control_repository)
    _record_control(workspace_id=workspace_id, agent_id=detail.agent_id, agent_run_id=agent_run_id, monitoring_import_id=detail.monitoring_import_id, action=action, event_type=event_type, payload=payload, principal=principal, control_repository=control_repository, audit_repository=audit_repository, metadata={})
    return success_response(data={**detail.model_dump(mode="json"), "status": "paused" if action == "pause" else "stopped" if action == "stop" else "queued" if action == "resume" else detail.status})


def _record_control(*, workspace_id: UUID, agent_id: str, agent_run_id: UUID | None, monitoring_import_id: UUID | None, action: str, event_type: str, payload: AgentControlRequest, principal: WorkspacePrincipal, control_repository: AgentControlRepository, audit_repository: AuditLogRepository, metadata: dict) -> None:
    control_repository.record_control_action(workspace_id=workspace_id, agent_id=agent_id, agent_run_id=agent_run_id, monitoring_import_id=monitoring_import_id, action=action, actor_user_id=principal.user_id, reason=payload.reason, metadata_json={**metadata, "execution_boundary": "no_live_amazon_change"})
    control_repository.insert_event(event=new_agent_event(workspace_id=workspace_id, agent_id=agent_id, agent_run_id=agent_run_id, monitoring_import_id=monitoring_import_id, event_type=event_type, message=payload.reason, metadata_json={**metadata, "controlled_by": principal.user_id, "execution_boundary": "no_live_amazon_change"}))
    audit_repository.record(workspace_id=workspace_id, actor_user_id=principal.user_id, action=f"agent.{action}", entity_type="agent_run" if agent_run_id else "agent_workflow", entity_id=agent_run_id or monitoring_import_id or uuid4(), details={"agent_id": agent_id, "reason": payload.reason, **metadata, "execution_boundary": "no_live_amazon_change"})


def _run_detail(run: AiRun, *, control_repository: AgentControlRepository, monitoring_import_id_filter: UUID | None = None) -> AgentRunDetail:
    control = run.output_json.get("_agent_control", {}) if isinstance(run.output_json, dict) else {}
    agent_id = str(control.get("agent_id") or agent_id_for_run_name(run.agent_name))
    monitoring_import_id = _uuid_or_none(control.get("monitoring_import_id"))
    latest_action = control_repository.latest_control_action(workspace_id=run.workspace_id, agent_id=agent_id, monitoring_import_id=monitoring_import_id, agent_run_id=run.id)
    status = "paused" if latest_action and latest_action.get("action") == "pause" else "stopped" if latest_action and latest_action.get("action") == "stop" else run.status
    return AgentRunDetail(
        id=run.id,
        workspace_id=run.workspace_id,
        product_id=run.product_id,
        monitoring_import_id=monitoring_import_id,
        agent_id=agent_id,
        agent_name=run.agent_name,
        provider=run.provider,
        model=run.model,
        schema_version=run.schema_version,
        input_hash=run.input_hash,
        input_json=control.get("input_json") or run.output_json.get("input_json", {}) if isinstance(run.output_json, dict) else {},
        output_json=run.output_json,
        error_json={"error": run.output_json.get("error"), "validation_errors": run.output_json.get("validation_errors", [])} if isinstance(run.output_json, dict) and (run.output_json.get("error") or run.output_json.get("validation_errors")) else {},
        status=status,
        latency_ms=run.latency_ms,
        mode=control.get("mode"),
        strictness_level=control.get("strictness_level"),
        confidence_threshold=control.get("confidence_threshold"),
        dependency_agent_run_ids=list(control.get("dependency_agent_run_ids") or []),
        recommendation_ids=list(control.get("recommendation_ids") or []),
        created_at=run.created_at,
        started_at=run.created_at,
        completed_at=run.created_at if run.status in {"succeeded", "failed", "skipped"} else None,
        stopped_at=latest_action.get("created_at") if latest_action and latest_action.get("action") == "stop" else None,
        paused_at=latest_action.get("created_at") if latest_action and latest_action.get("action") == "pause" else None,
        controlled_by=str(latest_action.get("actor_user_id")) if latest_action else None,
        control_reason=latest_action.get("reason") if latest_action else None,
        can_mutate_live_amazon_ads=False,
    )


def _workflow_node(*, agent_id: str, runs: list[AgentRunDetail], config: AgentConfig) -> AgentWorkflowNode:
    definition = AGENT_DEFINITION_BY_ID[agent_id]
    agent_runs = [run for run in runs if run.agent_id == agent_id]
    latest = sorted(agent_runs, key=lambda item: item.created_at, reverse=True)[0] if agent_runs else None
    status = latest.status if latest else "skipped" if not config.enabled else "pending"
    return AgentWorkflowNode(agent_id=agent_id, display_name=definition.display_name, description=definition.description, status=status, mode=config.mode.value, strictness_level=config.strictness_level.value, last_run_at=latest.created_at if latest else None, recommendations_created=len(latest.recommendation_ids) if latest else 0, errors=list(latest.error_json.get("validation_errors", [])) if latest else [], can_mutate_live_amazon_ads=False)


def _workflow_edges(*, nodes: list[AgentWorkflowNode], events) -> list[AgentWorkflowEdge]:
    node_status = {node.agent_id: node.status for node in nodes}
    pairs = [
        ("report_upload_node", "report_detection_agent"),
        ("report_detection_agent", "product_resolution_agent"),
        ("product_resolution_agent", "metrics_analysis_agent"),
        ("metrics_analysis_agent", "ai_recommendation_brain_agent"),
        ("ai_recommendation_brain_agent", "bid_optimization_agent"),
        ("ai_recommendation_brain_agent", "negative_keyword_agent"),
        ("ai_recommendation_brain_agent", "budget_allocation_agent"),
        ("ai_recommendation_brain_agent", "pause_review_agent"),
        ("bid_optimization_agent", "stakeholder_reporting_agent"),
        ("negative_keyword_agent", "stakeholder_reporting_agent"),
        ("budget_allocation_agent", "stakeholder_reporting_agent"),
        ("pause_review_agent", "stakeholder_reporting_agent"),
        ("stakeholder_reporting_agent", "human_approval_agent"),
    ]
    created_at = _event_created_at(events[0]) if events else None
    completed_at = _event_created_at(events[-1]) if events else None
    return [AgentWorkflowEdge(source_agent_id=source, target_agent_id=target, status=_edge_status(node_status.get(source, "pending"), node_status.get(target, "pending")), data_passed_summary=EDGE_SUMMARIES[(source, target)], created_at=created_at, completed_at=completed_at) for source, target in pairs]


def _edge_status(source_status: str, target_status: str) -> str:
    if source_status in {"failed", "stopped"}:
        return "blocked"
    if target_status in {"succeeded", "failed", "skipped", "stopped", "paused"}:
        return target_status
    if source_status == "succeeded":
        return "ready"
    return "waiting_for_dependency"


def _find_run(*, workspace_id: UUID, agent_run_id: UUID, monitoring_repository: MonitoringRepository) -> AiRun | None:
    return next((run for run in monitoring_repository.list_ai_runs(workspace_id=workspace_id) if run.id == agent_run_id), None)


def _ensure_agent(agent_id: str) -> None:
    if agent_id not in AGENT_DEFINITION_BY_ID:
        raise ApiError(code="AGENT_NOT_FOUND", message="Agent definition was not found.", status_code=404)


def _event_created_at(event):
    return event.get("created_at") if isinstance(event, dict) else event.created_at


def _uuid_or_none(value) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None
