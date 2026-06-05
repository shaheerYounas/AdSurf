from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID, uuid4

from apps.api.app.domain.monitoring import AGENT_SCHEMA_VERSION
from apps.api.app.schemas.account_imports import AccountImport, AccountImportEntity, EntityType
from apps.api.app.schemas.agent_control import AgentConfig
from apps.api.app.schemas.monitoring import (
    AiRun,
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.services.agent_registry import AGENT_DEFINITION_BY_ID, AGENT_WORKFLOW_ORDER


ACCOUNT_AGENT_SCHEMA_VERSION = "account_bulk_agent_workflow_v1"
ACCOUNT_DECISION_SOURCE = "account_bulk_deterministic_agents"


def build_account_agent_workflow_runs(
    *,
    workspace_id: UUID,
    import_record: AccountImport,
    entities: list[AccountImportEntity],
    configs: dict[str, AgentConfig],
) -> tuple[list[AiRun], list[Recommendation]]:
    recommendations = _build_account_recommendations(workspace_id=workspace_id, import_record=import_record, entities=entities)
    runs: list[AiRun] = []
    dependency_ids: list[str] = []
    recommendation_ids = [str(item.id) for item in recommendations]
    account_metrics = _account_metrics(entities)
    entity_counts = _entity_counts(entities)

    for agent_id in AGENT_WORKFLOW_ORDER:
        definition = AGENT_DEFINITION_BY_ID[agent_id]
        config = configs.get(agent_id)
        status = "skipped" if config and not config.enabled and definition.can_be_disabled else "succeeded"
        output = _agent_output(
            agent_id=agent_id,
            import_record=import_record,
            entities=entities,
            recommendations=recommendations,
            account_metrics=account_metrics,
            entity_counts=entity_counts,
            status=status,
        )
        run = _run(
            workspace_id=workspace_id,
            agent_id=agent_id,
            agent_name=agent_id,
            output=output,
            status=status,
            config=config,
            dependency_agent_run_ids=dependency_ids,
            recommendation_ids=recommendation_ids if agent_id in {"ai_recommendation_brain_agent", "human_approval_agent"} else _specialist_recommendation_ids(agent_id, recommendations),
            account_import_id=import_record.id,
        )
        runs.append(run)
        dependency_ids.append(str(run.id))

    recommendation_run = next((run for run in runs if run.agent_name == "ai_recommendation_brain_agent"), runs[0] if runs else None)
    if recommendation_run is None:
        return runs, recommendations
    return runs, [item.model_copy(update={"agent_run_id": recommendation_run.id, "ai_run_id": recommendation_run.id}) for item in recommendations]


def build_account_workflow_events(*, workspace_id: UUID, account_import_id: UUID, runs: list[AiRun]) -> list[dict]:
    events = []
    for run in sorted(runs, key=lambda item: item.created_at):
        control = run.output_json.get("_agent_control", {})
        events.extend(
            [
                _event(workspace_id, account_import_id, run, "agent_started", f"{control.get('display_name', run.agent_name)} started."),
                _event(workspace_id, account_import_id, run, "input_prepared", "Grouped account import evidence prepared."),
                _event(workspace_id, account_import_id, run, "output_validated", "Output validated inside approval boundary."),
            ]
        )
        if control.get("recommendation_ids"):
            events.append(_event(workspace_id, account_import_id, run, "recommendations_created", f"{len(control['recommendation_ids'])} recommendations created. Human approval required."))
        events.append(_event(workspace_id, account_import_id, run, "agent_succeeded" if run.status == "succeeded" else "agent_skipped", f"{control.get('display_name', run.agent_name)} finished with status {run.status}."))
    events.append(
        {
            "id": uuid4(),
            "workspace_id": workspace_id,
            "agent_id": "human_approval_agent",
            "agent_run_id": str(runs[-1].id) if runs else None,
            "monitoring_import_id": str(account_import_id),
            "event_type": "waiting_for_human",
            "message": "Recommendations are queued for human approval. No live Amazon Ads change executed.",
            "metadata_json": {"account_import_id": str(account_import_id), "execution_boundary": "no_live_amazon_change"},
            "created_at": datetime.now(UTC),
        }
    )
    return events


def _build_account_recommendations(*, workspace_id: UUID, import_record: AccountImport, entities: list[AccountImportEntity]) -> list[Recommendation]:
    now = datetime.now(UTC)
    recommendations: list[Recommendation] = []
    for entity in entities:
        recommendation_type = _recommendation_type(entity)
        if recommendation_type is None:
            continue
        priority = _priority(entity, recommendation_type)
        confidence = _confidence(entity)
        summary = _summary(entity, recommendation_type)
        recommendations.append(
            Recommendation(
                id=uuid4(),
                workspace_id=workspace_id,
                product_id=entity.product_id,
                monitoring_import_id=None,
                snapshot_id=None,
                account_import_id=import_record.id,
                entity_key=entity.entity_key,
                decision_source=ACCOUNT_DECISION_SOURCE,
                recommendation_type=recommendation_type,
                entity_type=RecommendationEntityType(entity.entity_type.value),
                status=RecommendationStatus.PENDING_APPROVAL,
                priority=priority,
                confidence=confidence,
                rule_version_id=ACCOUNT_AGENT_SCHEMA_VERSION,
                rule_name="account_bulk_deterministic_agent_workflow",
                campaign_name=entity.campaign_name,
                ad_group_name=entity.ad_group_name,
                targeting=entity.targeting,
                customer_search_term=entity.customer_search_term,
                input_metrics_json=entity.metrics_json,
                current_metric_snapshot_json=entity.metrics_json,
                evidence_json={
                    "decision_source": ACCOUNT_DECISION_SOURCE,
                    "account_import_id": str(import_record.id),
                    "entity_type": entity.entity_type.value,
                    "entity_key": entity.entity_key,
                    "resolution_status": entity.resolution_status.value,
                    "approval_boundary": _approval_boundary(),
                },
                proposed_action_json=_proposed_action(entity, recommendation_type),
                explanation_json={
                    "summary": summary,
                    "approval_required": True,
                    "decision_source": ACCOUNT_DECISION_SOURCE,
                    "execution_boundary": "recommendation_only_no_live_amazon_change",
                },
                approval_boundary=_approval_boundary(),
                created_at=now,
                updated_at=now,
            )
        )
    return recommendations[:100]


def _recommendation_type(entity: AccountImportEntity) -> RecommendationType | None:
    metrics = entity.metrics_json
    spend = _decimal(metrics.get("spend"))
    sales = _decimal(metrics.get("sales"))
    orders = int(_decimal(metrics.get("orders")))
    clicks = int(_decimal(metrics.get("clicks")))
    if entity.entity_type in {EntityType.PRODUCT, EntityType.ACCOUNT} and entity.resolution_status.value != "matched_existing_product":
        return RecommendationType.DATA_QUALITY_REVIEW
    if entity.entity_type == EntityType.SEARCH_TERM and spend >= Decimal("5") and orders == 0 and clicks > 0:
        return RecommendationType.ADD_NEGATIVE_EXACT
    if entity.entity_type in {EntityType.TARGET, EntityType.AD_GROUP} and spend >= Decimal("10") and orders == 0 and clicks > 0:
        return RecommendationType.PAUSE_REVIEW
    if entity.entity_type == EntityType.SEARCH_TERM and orders > 0 and sales >= spend * Decimal("2"):
        return RecommendationType.MOVE_TO_EXACT
    if entity.entity_type == EntityType.CAMPAIGN and orders >= 1 and sales > spend:
        return RecommendationType.BUDGET_REVIEW
    return None


def _priority(entity: AccountImportEntity, recommendation_type: RecommendationType) -> RecommendationPriority:
    spend = _decimal(entity.metrics_json.get("spend"))
    if recommendation_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.PAUSE_REVIEW} and spend >= Decimal("20"):
        return RecommendationPriority.HIGH
    if recommendation_type == RecommendationType.DATA_QUALITY_REVIEW:
        return RecommendationPriority.HIGH
    return RecommendationPriority.MEDIUM


def _confidence(entity: AccountImportEntity) -> RecommendationConfidence:
    clicks = _decimal(entity.metrics_json.get("clicks"))
    if clicks >= 10:
        return RecommendationConfidence.HIGH
    if clicks >= 3:
        return RecommendationConfidence.MEDIUM
    return RecommendationConfidence.LOW


def _summary(entity: AccountImportEntity, recommendation_type: RecommendationType) -> str:
    label = entity.customer_search_term or entity.targeting or entity.ad_group_name or entity.campaign_name or entity.product_name or entity.entity_key
    if recommendation_type == RecommendationType.ADD_NEGATIVE_EXACT:
        return f"{label} spent with clicks and no orders. Review as a negative exact recommendation before any manual action."
    if recommendation_type == RecommendationType.PAUSE_REVIEW:
        return f"{label} has inefficient spend and no orders. Review for pause consideration; AdSurf will not pause live ads."
    if recommendation_type == RecommendationType.MOVE_TO_EXACT:
        return f"{label} produced orders and efficient sales. Review for move-to-exact or scaling."
    if recommendation_type == RecommendationType.BUDGET_REVIEW:
        return f"{label} generated sales above spend. Review campaign budget allocation manually."
    return f"{label} needs product mapping or data quality review before deeper optimization."


def _proposed_action(entity: AccountImportEntity, recommendation_type: RecommendationType) -> dict:
    return {
        "action": recommendation_type.value,
        "action_level": entity.entity_type.value,
        "campaign_name": entity.campaign_name,
        "ad_group_name": entity.ad_group_name,
        "targeting": entity.targeting,
        "customer_search_term": entity.customer_search_term,
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
        "amazon_ads_api_mutation": False,
    }


def _agent_output(*, agent_id: str, import_record: AccountImport, entities: list[AccountImportEntity], recommendations: list[Recommendation], account_metrics: dict, entity_counts: dict, status: str) -> dict:
    base = {
        "account_import_id": str(import_record.id),
        "status": status,
        "execution_boundary": "recommendation_only_no_live_amazon_change",
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    }
    if agent_id == "report_detection_agent":
        return {**base, "detected_report_type": import_record.detected_report_type.value, "confidence": import_record.detection_confidence.value, "warnings": import_record.data_quality_warnings_json}
    if agent_id == "product_resolution_agent":
        return {**base, "entity_counts": entity_counts, "products_detected": entity_counts.get("product", 0), "needs_mapping": [item.entity_key for item in entities if item.resolution_status.value != "matched_existing_product" and item.entity_type == EntityType.PRODUCT][:25]}
    if agent_id == "metrics_analysis_agent":
        return {**base, "account_metrics": account_metrics, "entity_counts": entity_counts, "top_spend_entities": _top_entities(entities, "spend")}
    if agent_id == "ai_recommendation_brain_agent":
        return {**base, "recommendation_count": len(recommendations), "recommendations": [_compact_recommendation(item) for item in recommendations[:25]]}
    if agent_id == "human_approval_agent":
        return {**base, "pending_approvals": len(recommendations), "approval_note": "Humans must approve or reject. No live Amazon Ads change executed."}
    return {**base, "recommendation_count": len(_specialist_recommendations(agent_id, recommendations)), "recommendations": [_compact_recommendation(item) for item in _specialist_recommendations(agent_id, recommendations)[:25]]}


def _run(*, workspace_id: UUID, agent_id: str, agent_name: str, output: dict, status: str, config: AgentConfig | None, dependency_agent_run_ids: list[str], recommendation_ids: list[str], account_import_id: UUID) -> AiRun:
    definition = AGENT_DEFINITION_BY_ID[agent_id]
    input_json = {"account_import_id": str(account_import_id), "agent_config": config.model_dump(mode="json") if config else {}, "safety": _approval_boundary()}
    control = {
        "agent_id": agent_id,
        "display_name": definition.display_name,
        "monitoring_import_id": str(account_import_id),
        "account_import_id": str(account_import_id),
        "input_json": input_json,
        "mode": config.mode.value if config else "hybrid",
        "strictness_level": config.strictness_level.value if config else "balanced",
        "confidence_threshold": config.confidence_threshold.value if config else "medium",
        "dependency_agent_run_ids": dependency_agent_run_ids,
        "recommendation_ids": recommendation_ids,
    }
    payload = {**output, "_agent_control": control}
    return AiRun(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=None,
        agent_name=agent_name,
        provider=(config.provider.value if config else "deterministic"),
        model=config.model or "account-bulk-deterministic-v1" if config else "account-bulk-deterministic-v1",
        schema_version=AGENT_SCHEMA_VERSION,
        input_hash=sha256(json.dumps(input_json, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        output_json=payload,
        status=status,
        latency_ms=0,
        created_at=datetime.now(UTC),
    )


def _event(workspace_id: UUID, account_import_id: UUID, run: AiRun, event_type: str, message: str) -> dict:
    control = run.output_json.get("_agent_control", {})
    return {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "agent_id": control.get("agent_id", run.agent_name),
        "agent_run_id": str(run.id),
        "monitoring_import_id": str(account_import_id),
        "event_type": event_type,
        "message": message,
        "metadata_json": {"account_import_id": str(account_import_id), "workspace_id": str(workspace_id), "execution_boundary": "no_live_amazon_change"},
        "created_at": run.created_at,
    }


def _specialist_recommendation_ids(agent_id: str, recommendations: list[Recommendation]) -> list[str]:
    return [str(item.id) for item in _specialist_recommendations(agent_id, recommendations)]


def _specialist_recommendations(agent_id: str, recommendations: list[Recommendation]) -> list[Recommendation]:
    if agent_id == "bid_optimization_agent":
        return [item for item in recommendations if item.recommendation_type in {RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID, RecommendationType.MOVE_TO_EXACT}]
    if agent_id == "negative_keyword_agent":
        return [item for item in recommendations if item.recommendation_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}]
    if agent_id == "budget_allocation_agent":
        return [item for item in recommendations if item.recommendation_type == RecommendationType.BUDGET_REVIEW]
    if agent_id == "pause_review_agent":
        return [item for item in recommendations if item.recommendation_type == RecommendationType.PAUSE_REVIEW]
    if agent_id == "stakeholder_reporting_agent":
        return recommendations
    return []


def _account_metrics(entities: list[AccountImportEntity]) -> dict:
    account = next((item for item in entities if item.entity_type == EntityType.ACCOUNT), None)
    return account.metrics_json if account else {}


def _entity_counts(entities: list[AccountImportEntity]) -> dict:
    counts: dict[str, int] = {}
    for entity in entities:
        counts[entity.entity_type.value] = counts.get(entity.entity_type.value, 0) + 1
    return counts


def _top_entities(entities: list[AccountImportEntity], metric: str) -> list[dict]:
    return [
        {"entity_type": item.entity_type.value, "entity_key": item.entity_key, "metrics": item.metrics_json}
        for item in sorted(entities, key=lambda entity: _decimal(entity.metrics_json.get(metric)), reverse=True)[:10]
    ]


def _compact_recommendation(recommendation: Recommendation) -> dict:
    return {
        "id": str(recommendation.id),
        "type": recommendation.recommendation_type.value,
        "entity_type": recommendation.entity_type.value,
        "entity_key": recommendation.entity_key,
        "priority": recommendation.priority.value,
        "confidence": recommendation.confidence.value,
        "summary": recommendation.explanation_json.get("summary"),
    }


def _approval_boundary() -> dict:
    return {"requires_human_approval": True, "executes_live_amazon_change": False, "amazon_ads_api_mutation": False}


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))
