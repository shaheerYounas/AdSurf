from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from uuid import UUID

from apps.api.app.orchestration.checkpoints import persist_node_state
from apps.api.app.orchestration.events import checkpoint, emit_event
from apps.api.app.orchestration.graph_state import AdsWorkflowState, touch_state
from apps.api.app.orchestration.validation import validate_recommendation_payload
from apps.api.app.repositories.account_imports import AccountImportRepository
from apps.api.app.repositories.workflows import WorkflowRepository
from apps.api.app.schemas.account_imports import EntityType
from apps.api.app.schemas.workflows import WorkflowStatus


@dataclass(frozen=True)
class WorkflowNodeContext:
    workflow_repository: WorkflowRepository
    account_import_repository: AccountImportRepository


def start_workflow_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _run_node(
        "start_workflow",
        state,
        context,
        lambda current: {
            **touch_state(current, node_name="start_workflow", status=WorkflowStatus.RUNNING.value),
            "human_approval_required": True,
        },
        "Workflow started. Agents may create recommendations only; human approval is required.",
    )


def report_detection_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        account_import = _load_account_import(current, context)
        warnings = list(current.get("warnings", []))
        warnings.extend(account_import.data_quality_warnings_json)
        return {
            **touch_state(current, node_name="report_detection", status=WorkflowStatus.RUNNING.value),
            "upload_id": str(account_import.upload_id),
            "report_type": account_import.report_type.value,
            "detected_report_type": account_import.detected_report_type.value,
            "detection_confidence": account_import.detection_confidence.value,
            "rows_count": account_import.total_rows,
            "parsed_rows_ref": str(account_import.parse_run_id),
            "warnings": warnings,
        }

    return _run_node("report_detection", state, context, work, "Report type and data readiness detected.", agent_id="report_detection_agent")


def product_resolution_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        entities = _load_entities(current, context)
        product_entities = [entity for entity in entities if entity.entity_type == EntityType.PRODUCT]
        mappings = [
            {
                "entity_key": entity.entity_key,
                "product_id": str(entity.product_id) if entity.product_id else None,
                "asin": entity.asin,
                "sku": entity.sku,
                "product_name": entity.product_name,
                "resolution_status": entity.resolution_status.value,
            }
            for entity in product_entities
        ]
        grouped = {
            entity.entity_key: {
                "entity_type": entity.entity_type.value,
                "product_id": str(entity.product_id) if entity.product_id else None,
                "asin": entity.asin,
                "sku": entity.sku,
                "campaign_name": entity.campaign_name,
                "ad_group_name": entity.ad_group_name,
                "targeting": entity.targeting,
                "customer_search_term": entity.customer_search_term,
                "metrics": entity.metrics_json,
            }
            for entity in entities
        }
        warnings = list(current.get("warnings", []))
        if any(mapping["resolution_status"] != "matched_existing_product" for mapping in mappings):
            warnings.append({"code": "PRODUCT_MAPPING_REVIEW_REQUIRED", "message": "Some detected products need human mapping before high-confidence product-level analysis."})
        return {
            **touch_state(current, node_name="product_resolution", status=WorkflowStatus.RUNNING.value),
            "product_mappings": mappings,
            "grouped_entities": grouped,
            "warnings": warnings,
        }

    return _run_node("product_resolution", state, context, work, "Product, campaign, ad group, target, and search-term groups prepared.", agent_id="product_resolution_agent")


def metrics_analysis_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        grouped_entities = current.get("grouped_entities") or {}
        by_type: dict[str, list[dict]] = {}
        account_metrics = {}
        for entity_key, entity in grouped_entities.items():
            entity_type = entity.get("entity_type", "unknown")
            by_type.setdefault(entity_type, []).append({"entity_key": entity_key, **entity})
            if entity_type == "account":
                account_metrics = entity.get("metrics", {})
        rollups = {
            "account": account_metrics,
            "entity_counts": {entity_type: len(items) for entity_type, items in by_type.items()},
            "top_spend_entities": sorted(
                [
                    {"entity_key": key, "entity_type": value.get("entity_type"), "spend": _decimal(value.get("metrics", {}).get("spend"))}
                    for key, value in grouped_entities.items()
                ],
                key=lambda item: item["spend"],
                reverse=True,
            )[:10],
        }
        rollups["top_spend_entities"] = [{**item, "spend": str(item["spend"])} for item in rollups["top_spend_entities"]]
        return {
            **touch_state(current, node_name="metrics_analysis", status=WorkflowStatus.RUNNING.value),
            "metrics_rollups": rollups,
        }

    return _run_node("metrics_analysis", state, context, work, "Deterministic metric rollups calculated for the full import.", agent_id="metrics_analysis_agent")


def ai_recommendation_brain_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        grouped_entities = current.get("grouped_entities") or {}
        grouped_keys = set(grouped_entities.keys())
        agent_config = current.get("agent_config") or {}
        valid: list[dict] = []
        rejected: list[dict] = []
        for recommendation in _deterministic_recommendations(grouped_entities):
            is_valid, errors = validate_recommendation_payload(
                recommendation=recommendation,
                grouped_entity_keys=grouped_keys,
                agent_config=agent_config,
            )
            if is_valid:
                valid.append(recommendation)
            else:
                rejected.append({"recommendation": recommendation, "validation_errors": errors})
        return {
            **touch_state(current, node_name="ai_recommendation_brain", status=WorkflowStatus.RUNNING.value),
            "recommendations": valid,
            "rejected_recommendations": rejected,
        }

    return _run_node("ai_recommendation_brain", state, context, work, "Recommendation decisions generated inside approval-only boundaries.", agent_id="ai_recommendation_brain_agent")


def bid_optimization_agent_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _specialist_node("bid_optimization", "bid_optimization_agent", state, context)


def negative_keyword_agent_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _specialist_node("negative_keyword", "negative_keyword_agent", state, context)


def budget_allocation_agent_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _specialist_node("budget_allocation", "budget_allocation_agent", state, context)


def pause_review_agent_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _specialist_node("pause_review", "pause_review_agent", state, context)


def stakeholder_reporting_agent_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        recommendations = current.get("recommendations") or []
        summary = {
            "recommendation_count": len(recommendations),
            "pending_approval_count": len(recommendations),
            "safety_note": "Recommendation only. Requires human approval. No live Amazon Ads change executed.",
            "top_priorities": recommendations[:5],
        }
        return {
            **touch_state(current, node_name="stakeholder_reporting", status=WorkflowStatus.RUNNING.value),
            "dashboard_summary": summary,
        }

    return _run_node("stakeholder_reporting", state, context, work, "Approver summary prepared.", agent_id="stakeholder_reporting_agent")


def human_approval_gate_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        return {
            **touch_state(current, node_name="human_approval_gate", status=WorkflowStatus.WAITING_FOR_HUMAN.value),
            "human_approval_required": True,
            "dashboard_summary": {
                **(current.get("dashboard_summary") or {}),
                "approval_gate": "waiting_for_human",
                "approval_boundary": {
                    "recommendation_only": True,
                    "requires_human_approval": True,
                    "executes_live_amazon_change": False,
                },
            },
        }

    return _run_node("human_approval_gate", state, context, work, "Recommendations are waiting for human approval. No live Amazon Ads change executed.", agent_id="human_approval_agent", status=WorkflowStatus.WAITING_FOR_HUMAN)


def finalize_workflow_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _run_node(
        "finalize_workflow",
        state,
        context,
        lambda current: touch_state(current, node_name="finalize_workflow", status=WorkflowStatus.SUCCEEDED.value),
        "Workflow finalized.",
        status=WorkflowStatus.SUCCEEDED,
        completed=True,
    )


def failure_node(state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    errors = state.get("errors") or [{"code": "WORKFLOW_FAILED", "message": "Agent workflow failed."}]
    workflow_id = UUID(state["workflow_id"])
    workspace_id = UUID(state["workspace_id"])
    failed_state = touch_state(state, node_name="failure", status=WorkflowStatus.FAILED.value)
    persist_node_state(
        context.workflow_repository,
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        node_name="failure",
        status=WorkflowStatus.FAILED,
        state_json=failed_state,
        error_json={"errors": errors},
        completed=True,
    )
    emit_event(
        context.workflow_repository,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        node_name="failure",
        event_type="node_failed",
        message="Workflow failed. No live Amazon Ads change executed.",
        metadata_json={"errors": errors},
    )
    return failed_state


def _specialist_node(node_name: str, agent_id: str, state: AdsWorkflowState, context: WorkflowNodeContext) -> AdsWorkflowState:
    return _run_node(
        node_name,
        state,
        context,
        lambda current: touch_state(current, node_name=node_name, status=WorkflowStatus.RUNNING.value),
        f"{node_name.replace('_', ' ').title()} completed approval-bound review.",
        agent_id=agent_id,
    )


def _run_node(
    node_name: str,
    state: AdsWorkflowState,
    context: WorkflowNodeContext,
    work,
    success_message: str,
    *,
    agent_id: str | None = None,
    status: WorkflowStatus = WorkflowStatus.RUNNING,
    completed: bool = False,
) -> AdsWorkflowState:
    workflow_id = UUID(state["workflow_id"])
    workspace_id = UUID(state["workspace_id"])
    started = perf_counter()
    emit_event(
        context.workflow_repository,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        node_name=node_name,
        agent_id=agent_id,
        event_type="node_started",
        message=f"{node_name} started.",
    )
    try:
        updated = work(state)
        persist_node_state(
            context.workflow_repository,
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            node_name=node_name,
            status=status,
            state_json=updated,
            completed=completed,
        )
        checkpoint(context.workflow_repository, workflow_id=workflow_id, node_name=node_name, state_json=updated, status=status)
        emit_event(
            context.workflow_repository,
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            node_name=node_name,
            agent_id=agent_id,
            event_type="node_completed" if not completed else "workflow_completed",
            message=success_message,
            metadata_json={"approval_boundary": updated.get("safety_boundaries", {})},
            latency_ms=int((perf_counter() - started) * 1000),
        )
        trace_ids = list(updated.get("trace_ids") or [])
        updated["trace_ids"] = trace_ids
        return updated
    except Exception as exc:  # noqa: BLE001 - failures must be traced and routed.
        errored = touch_state(state, node_name=node_name, status=WorkflowStatus.FAILED.value)
        errors = list(errored.get("errors") or [])
        errors.append({"code": "NODE_FAILED", "node_name": node_name, "message": str(exc)})
        errored["errors"] = errors
        emit_event(
            context.workflow_repository,
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            node_name=node_name,
            agent_id=agent_id,
            event_type="node_failed",
            message=f"{node_name} failed. No live Amazon Ads change executed.",
            metadata_json={"error": str(exc)},
            latency_ms=int((perf_counter() - started) * 1000),
        )
        return errored


def _load_account_import(state: AdsWorkflowState, context: WorkflowNodeContext):
    account_import_id = state.get("account_import_id")
    if not account_import_id:
        raise ValueError("account_import_id is required")
    import_record = context.account_import_repository.get_import(
        workspace_id=UUID(state["workspace_id"]),
        account_import_id=UUID(account_import_id),
    )
    if import_record is None:
        raise ValueError("account import was not found")
    return import_record


def _load_entities(state: AdsWorkflowState, context: WorkflowNodeContext):
    account_import_id = state.get("account_import_id")
    if not account_import_id:
        return []
    return context.account_import_repository.list_entities(
        workspace_id=UUID(state["workspace_id"]),
        account_import_id=UUID(account_import_id),
    )


def _deterministic_recommendations(grouped_entities: dict) -> list[dict]:
    recommendations = []
    for entity_key, entity in grouped_entities.items():
        metrics = entity.get("metrics", {})
        spend = _decimal(metrics.get("spend"))
        sales = _decimal(metrics.get("sales"))
        orders = int(_decimal(metrics.get("orders")))
        clicks = int(_decimal(metrics.get("clicks")))
        entity_type = entity.get("entity_type")
        recommendation_type = None
        if entity_type == "search_term" and spend >= Decimal("5") and orders == 0 and clicks > 0:
            recommendation_type = "add_negative_exact"
        elif entity_type in {"target", "ad_group"} and spend >= Decimal("10") and orders == 0 and clicks > 0:
            recommendation_type = "pause_review"
        elif entity_type == "campaign" and orders >= 1 and sales > spend:
            recommendation_type = "budget_review"
        if not recommendation_type:
            continue
        recommendations.append(
            {
                "scope_level": entity_type,
                "entity_type": entity_type,
                "entity_key": entity_key,
                "product_id": entity.get("product_id"),
                "asin": entity.get("asin"),
                "sku": entity.get("sku"),
                "campaign_name": entity.get("campaign_name"),
                "ad_group_name": entity.get("ad_group_name"),
                "targeting": entity.get("targeting"),
                "customer_search_term": entity.get("customer_search_term"),
                "recommendation_type": recommendation_type,
                "priority": "high" if spend >= Decimal("20") else "medium",
                "confidence": "high" if clicks >= 10 else "medium",
                "reasoning_summary": "Deterministic account workflow found metric evidence for a review-only recommendation.",
                "evidence": metrics,
                "proposed_action": {
                    "action": recommendation_type,
                    "requires_human_approval": True,
                    "executes_live_amazon_change": False,
                },
                "risk_note": "Review before approval. AdSurf has not changed live Amazon Ads.",
                "approval_required": True,
                "executes_live_amazon_change": False,
            }
        )
    return recommendations[:100]


def _decimal(value) -> Decimal:
    if value in {None, ""}:
        return Decimal("0")
    return Decimal(str(value))
