from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from time import perf_counter
from uuid import UUID, uuid4

from apps.api.app.core.observability import get_tracer, set_workspace_context, SpanKind
from apps.api.app.orchestration.checkpoints import persist_node_state
from apps.api.app.orchestration.events import checkpoint, emit_event
from apps.api.app.orchestration.graph_state import AdsWorkflowState, touch_state
from apps.api.app.orchestration.validation import validate_recommendation_payload
from apps.api.app.repositories.account_imports import AccountImportRepository
from apps.api.app.repositories.monitoring import MonitoringRepository
from apps.api.app.repositories.workflows import WorkflowRepository
from apps.api.app.schemas.account_imports import AccountImportEntity, EntityType
from apps.api.app.schemas.agent_control import AgentConfig
from apps.api.app.schemas.monitoring import Recommendation, RecommendationConfidence, RecommendationEntityType, RecommendationPriority, RecommendationStatus, RecommendationType
from apps.api.app.schemas.workflows import WorkflowStatus
from apps.api.app.services.ai_client import AiClientError
from apps.api.app.services.ai_provider_factory import build_agent_ai_client


@dataclass(frozen=True)
class WorkflowNodeContext:
    workflow_repository: WorkflowRepository
    account_import_repository: AccountImportRepository
    monitoring_repository: MonitoringRepository


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
        agent_config = _agent_config_for(current, "ai_recommendation_brain_agent")
        recommendations, llm_metadata = _ai_or_deterministic_recommendations(current=current, grouped_entities=grouped_entities, agent_config=agent_config, context=context)
        valid: list[dict] = []
        rejected: list[dict] = list(current.get("rejected_recommendations") or [])
        for recommendation in recommendations:
            is_valid, errors = validate_recommendation_payload(
                recommendation=recommendation,
                grouped_entity_keys=grouped_keys,
                agent_config=agent_config,
            )
            if is_valid:
                valid.append(recommendation)
            else:
                rejected.append({"recommendation": recommendation, "validation_errors": errors})
        next_status = WorkflowStatus.FAILED.value if current.get("errors") and not valid else WorkflowStatus.RUNNING.value
        return {
            **touch_state(current, node_name="ai_recommendation_brain", status=next_status),
            "recommendations": valid,
            "rejected_recommendations": rejected,
            "llm_metadata": llm_metadata,
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
        if not current.get("recommendations") and current.get("grouped_entities"):
            current = {
                **current,
                "recommendations": _deterministic_recommendations(current.get("grouped_entities") or {}),
                "llm_metadata": {**(current.get("llm_metadata") or {}), "used_ai": False, "fallback_used": True, "fallback_reason": "No recommendation candidates were available before approval gate."},
            }
        recommendation_ids = _persist_recommendations(current, context)
        gate_id = context.workflow_repository.create_human_approval_gate(
            workflow_id=UUID(current["workflow_id"]),
            workspace_id=UUID(current["workspace_id"]),
            gate_type="recommendation_review",
            requested_action_json={"recommendation_ids": recommendation_ids, "approval_required": True, "executes_live_amazon_change": False},
            evidence_json={"account_import_id": current.get("account_import_id"), "recommendation_count": len(recommendation_ids), "safety_boundaries": current.get("safety_boundaries", {})},
        )
        return {
            **touch_state(current, node_name="human_approval_gate", status=WorkflowStatus.WAITING_FOR_HUMAN.value),
            "human_approval_required": True,
            "persisted_recommendation_ids": recommendation_ids,
            "human_approval_gate_id": str(gate_id),
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
    """Specialist nodes support both deterministic and AI-driven explanations.
    
    The node records its execution but the actual dual-path decisions are
    computed by the specialist services (DualPathMonitoringAgentsExplain, etc.).
    The agent_config.mode determines whether deterministic rules, AI, or hybrid
    is used for the explanation/review output.
    """
    def work(current: AdsWorkflowState) -> AdsWorkflowState:
        agent_config = _agent_config_for(current, agent_id)
        mode = str(agent_config.get("mode", "hybrid"))
        updated = touch_state(current, node_name=node_name, status=WorkflowStatus.RUNNING.value)
        return {
            **updated,
            f"{node_name}_mode": mode,
            f"{node_name}_decision_source": "deterministic" if mode == "deterministic" else "hybrid",
            f"{node_name}_approval_boundary": _approval_boundary(),
        }
    
    return _run_node(
        node_name,
        state,
        context,
        work,
        f"{node_name.replace('_', ' ').title()} completed approval-bound review (deterministic + AI dual-path enabled).",
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
    workspace_id_str = state.get("workspace_id") if hasattr(state, "get") else str(workspace_id)
    set_workspace_context(str(workspace_id_str))

    started = perf_counter()
    tracer = get_tracer()

    with tracer.span(
        f"node.{node_name}",
        kind=SpanKind.WORKFLOW,
        workspace_id=str(workspace_id),
        agent_id=agent_id,
    ) as trace_span:
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
            latency = int((perf_counter() - started) * 1000)
            trace_span.set_attribute("latency_ms", latency)
            trace_span.set_attribute("status", str(status.value))
            trace_span.set_attribute("completed", completed)
            emit_event(
                context.workflow_repository,
                workflow_id=workflow_id,
                workspace_id=workspace_id,
                node_name=node_name,
                agent_id=agent_id,
                event_type="node_completed" if not completed else "workflow_completed",
                message=success_message,
                metadata_json={"approval_boundary": updated.get("safety_boundaries", {}), "trace_latency_ms": latency},
                latency_ms=latency,
            )
            trace_ids = list(updated.get("trace_ids") or [])
            updated["trace_ids"] = trace_ids
            trace_span.add_event("node_completed", latency_ms=latency)
            return updated
        except Exception as exc:  # noqa: BLE001 - failures must be traced and routed.
            latency = int((perf_counter() - started) * 1000)
            trace_span.set_attribute("error", str(exc))
            trace_span.set_attribute("latency_ms", latency)
            trace_span.add_event("node_failed", error=str(exc), latency_ms=latency)
            trace_span.finish(status="error")
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
                latency_ms=latency,
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


def _ai_or_deterministic_recommendations(*, current: AdsWorkflowState, grouped_entities: dict, agent_config: dict, context: WorkflowNodeContext) -> tuple[list[dict], dict]:
    mode = str(agent_config.get("mode") or "hybrid")
    provider = str(agent_config.get("provider") or "deepseek")
    if mode == "deterministic" or provider == "deterministic":
        return _deterministic_recommendations(grouped_entities), {"used_ai": False, "provider": "deterministic", "fallback_used": False}

    messages = _ai_messages(current=current, grouped_entities=grouped_entities, agent_config=agent_config)
    prompt_hash = sha256(json.dumps({"messages": messages}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    try:
        client = build_agent_ai_client(agent_id="ai_recommendation_brain_agent", agent_config=agent_config)
        emit_event(
            context.workflow_repository,
            workflow_id=UUID(current["workflow_id"]),
            workspace_id=UUID(current["workspace_id"]),
            node_name="ai_recommendation_brain",
            agent_id="ai_recommendation_brain_agent",
            event_type="llm_call_started",
            message=f"{client.provider} called for account-level recommendations.",
            metadata_json={"provider": client.provider, "model": client.model},
            provider=client.provider,
            model=client.model,
        )
        response = client.complete_json(messages=messages)
        raw_recommendations = response.content_json.get("recommendations", [])
        recommendations = [_normalize_ai_recommendation(item) for item in raw_recommendations if isinstance(item, dict)]
        context.workflow_repository.insert_llm_call(
            workflow_id=UUID(current["workflow_id"]),
            agent_id="ai_recommendation_brain_agent",
            provider=response.provider,
            model=response.model,
            prompt_hash=prompt_hash,
            input_summary_json={"account_import_id": current.get("account_import_id"), "group_count": len(grouped_entities), "row_count": current.get("rows_count")},
            output_json=response.content_json,
            error_json={},
            status="succeeded",
            latency_ms=response.latency_ms,
        )
        emit_event(
            context.workflow_repository,
            workflow_id=UUID(current["workflow_id"]),
            workspace_id=UUID(current["workspace_id"]),
            node_name="ai_recommendation_brain",
            agent_id="ai_recommendation_brain_agent",
            event_type="llm_call_completed",
            message=f"{response.provider} returned {len(recommendations)} recommendation candidates.",
            metadata_json={"provider": response.provider, "model": response.model, "candidate_count": len(recommendations)},
            latency_ms=response.latency_ms,
            provider=response.provider,
            model=response.model,
        )
        if recommendations:
            return recommendations[: int(agent_config.get("max_recommendations") or 100)], {"used_ai": True, "provider": response.provider, "model": response.model, "fallback_used": False}
        raise AiClientError("AI returned no recommendation candidates.")
    except Exception as exc:  # noqa: BLE001 - provider failures must fall back safely.
        context.workflow_repository.insert_llm_call(
            workflow_id=UUID(current["workflow_id"]),
            agent_id="ai_recommendation_brain_agent",
            provider=provider,
            model=str(agent_config.get("model") or "default"),
            prompt_hash=prompt_hash,
            input_summary_json={"account_import_id": current.get("account_import_id"), "group_count": len(grouped_entities), "row_count": current.get("rows_count")},
            output_json={},
            error_json={"message": str(exc)},
            status="failed",
            latency_ms=0,
        )
        emit_event(
            context.workflow_repository,
            workflow_id=UUID(current["workflow_id"]),
            workspace_id=UUID(current["workspace_id"]),
            node_name="ai_recommendation_brain",
            agent_id="ai_recommendation_brain_agent",
            event_type="fallback_used" if mode == "hybrid" else "llm_call_failed",
            message="AI provider failed; deterministic fallback used." if mode == "hybrid" else "AI provider failed.",
            metadata_json={"error": str(exc), "provider": provider, "fallback_allowed": mode == "hybrid"},
        )
        if mode == "ai":
            errors = list(current.get("errors") or [])
            errors.append({"code": "AI_PROVIDER_FAILED", "message": str(exc)})
            current["errors"] = errors
            return [], {"used_ai": False, "provider": provider, "fallback_used": False, "error": str(exc)}
        return _deterministic_recommendations(grouped_entities), {"used_ai": False, "provider": provider, "fallback_used": True, "error": str(exc)}


def _ai_messages(*, current: AdsWorkflowState, grouped_entities: dict, agent_config: dict) -> list[dict[str, str]]:
    payload = {
        "report_context": {
            "report_type": current.get("detected_report_type") or current.get("report_type"),
            "scope": "account_bulk_report",
            "row_count": current.get("rows_count", 0),
            "detected_products": current.get("product_mappings", []),
        },
        "agent_config": agent_config,
        "grouped_metrics": {
            "account": current.get("metrics_rollups", {}).get("account", {}),
            "entities": [{"entity_key": key, **value} for key, value in grouped_entities.items()][: int(agent_config.get("max_groups_per_ai_call") or 100)],
        },
        "safety_boundaries": current.get("safety_boundaries", {}),
        "required_output_shape": {
            "recommendations": [
                {
                    "scope_level": "account | product | campaign | ad_group | target | search_term",
                    "entity_type": "account | product | campaign | ad_group | target | search_term",
                    "entity_key": "must match one provided entity_key",
                    "recommendation_type": "keep_running | increase_bid | decrease_bid | pause_review | add_negative_exact | add_negative_phrase | move_to_exact | data_quality_review | budget_review",
                    "priority": "critical | high | medium | low",
                    "confidence": "high | medium | low",
                    "reasoning_summary": "short approver-facing reason",
                    "evidence": {},
                    "proposed_action": {"requires_human_approval": True, "executes_live_amazon_change": False},
                    "risk_note": "short risk note",
                    "approval_required": True,
                    "executes_live_amazon_change": False,
                }
            ]
        },
    }
    system = (
        "You are AdSurf's AI Recommendation Brain for Amazon Ads account reports. "
        "Return strict JSON only. You may create recommendation decisions, but you must not approve, reject, "
        "execute, export, or claim live Amazon Ads changes. Every recommendation must require human approval "
        "and executes_live_amazon_change must be false."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, sort_keys=True, default=str)}]


def _normalize_ai_recommendation(item: dict) -> dict:
    proposed_action = item.get("proposed_action") or {}
    return {
        **item,
        "scope_level": item.get("scope_level") or item.get("entity_type"),
        "recommendation_type": item.get("recommendation_type") or item.get("type"),
        "priority": item.get("priority") or "medium",
        "confidence": item.get("confidence") or "medium",
        "evidence": item.get("evidence") or {},
        "reasoning_summary": item.get("reasoning_summary") or item.get("reasoning") or "",
        "proposed_action": {
            **proposed_action,
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        },
        "approval_required": True,
        "executes_live_amazon_change": False,
    }


def _persist_recommendations(state: AdsWorkflowState, context: WorkflowNodeContext) -> list[str]:
    if state.get("persisted_recommendation_ids"):
        return list(state["persisted_recommendation_ids"])
    account_import_id = state.get("account_import_id")
    if not account_import_id:
        return []
    workspace_id = UUID(state["workspace_id"])
    import_id = UUID(account_import_id)
    existing = [
        item
        for item in context.monitoring_repository.list_recommendations(workspace_id=workspace_id)
        if item.account_import_id == import_id and item.decision_source in {"langgraph_ai", "langgraph_deterministic"}
    ]
    if existing:
        return [str(item.id) for item in existing]
    entities = context.account_import_repository.list_entities(workspace_id=workspace_id, account_import_id=import_id)
    entity_by_key = {item.entity_key: item for item in entities}
    recommendations = [
        _recommendation_from_state_item(workspace_id=workspace_id, account_import_id=import_id, item=item, entity=entity_by_key.get(str(item.get("entity_key", ""))), decision_source="langgraph_ai" if state.get("llm_metadata", {}).get("used_ai") else "langgraph_deterministic")
        for item in state.get("recommendations", [])
        if item.get("recommendation_type")
    ]
    context.monitoring_repository.insert_recommendations(recommendations=[item for item in recommendations if item is not None])
    return [str(item.id) for item in recommendations if item is not None]


def _recommendation_from_state_item(*, workspace_id: UUID, account_import_id: UUID, item: dict, entity: AccountImportEntity | None, decision_source: str) -> Recommendation | None:
    try:
        recommendation_type = RecommendationType(str(item["recommendation_type"]))
        entity_type = RecommendationEntityType(str(item.get("entity_type") or item.get("scope_level") or "search_term"))
        priority = RecommendationPriority(str(item.get("priority") or "medium"))
        confidence = RecommendationConfidence(str(item.get("confidence") or "medium"))
    except ValueError:
        return None
    now = datetime.now(UTC)
    metrics = entity.metrics_json if entity else item.get("evidence", {})
    proposed_action = item.get("proposed_action") or {}
    return Recommendation(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=entity.product_id if entity else None,
        account_import_id=account_import_id,
        entity_key=str(item.get("entity_key") or (entity.entity_key if entity else "")),
        decision_source=decision_source,
        recommendation_type=recommendation_type,
        entity_type=entity_type,
        status=RecommendationStatus.PENDING_APPROVAL,
        priority=priority,
        confidence=confidence,
        rule_version_id="langgraph_account_workflow_v1",
        rule_name="langgraph_account_ai_recommendation_brain",
        campaign_name=item.get("campaign_name") or (entity.campaign_name if entity else None),
        ad_group_name=item.get("ad_group_name") or (entity.ad_group_name if entity else None),
        targeting=item.get("targeting") or (entity.targeting if entity else None),
        customer_search_term=item.get("customer_search_term") or (entity.customer_search_term if entity else None),
        input_metrics_json=metrics,
        current_metric_snapshot_json=metrics,
        evidence_json={
            "reasoning_summary": item.get("reasoning_summary"),
            "evidence": item.get("evidence"),
            "risk_note": item.get("risk_note"),
            "decision_source": decision_source,
            "approval_boundary": _approval_boundary(),
        },
        proposed_action_json={**proposed_action, "requires_human_approval": True, "executes_live_amazon_change": False, "amazon_ads_api_mutation": False},
        explanation_json={"summary": item.get("reasoning_summary") or "Review recommendation before approval.", "approval_required": True, "execution_boundary": "recommendation_only_no_live_amazon_change"},
        approval_boundary=_approval_boundary(),
        created_at=now,
        updated_at=now,
    )


def _agent_config_for(state: AdsWorkflowState, agent_id: str) -> dict:
    configs = state.get("agent_config") or {}
    if agent_id in configs and isinstance(configs[agent_id], dict):
        return configs[agent_id]
    return configs if isinstance(configs, dict) else {}


def _approval_boundary() -> dict:
    return {"requires_human_approval": True, "executes_live_amazon_change": False, "amazon_ads_api_mutation": False}


def _decimal(value) -> Decimal:
    if value in {None, ""}:
        return Decimal("0")
    return Decimal(str(value))
