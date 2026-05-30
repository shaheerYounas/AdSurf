from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.api.app.domain.monitoring import MONITORING_EVIDENCE_SCHEMA_VERSION
from apps.api.app.schemas.monitoring import (
    AiRun,
    MonitoringImport,
    MonitoringSnapshot,
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.services import monitoring_metrics
from apps.api.app.services import ai_confidence as confidence_module
from apps.api.app.services import ai_critic
from apps.api.app.services import optimization_memory
from apps.api.app.services.ai_client import AiClientError, AiJsonClient
from apps.api.app.services.deepseek_client import DeepSeekClient
from apps.api.app.services.monitoring_rules import build_recommendations


AI_RECOMMENDATION_AGENT_NAME = "monitoring_recommendation_brain"
AI_RECOMMENDATION_SCHEMA_VERSION = "monitoring_ai_recommendations_v1"
AI_RECOMMENDATION_MODES = {"deepseek", "deterministic_fallback", "hybrid"}
DEEPSEEK_DECISION_SOURCE = "deepseek_ai"
FALLBACK_DECISION_SOURCE = "fallback_rules"
DETERMINISTIC_DECISION_SOURCE = "deterministic_rules"

_LIVE_MUTATION_PHRASES = {
    "amazon ads api mutation",
    "call amazon ads api",
    "automatically apply",
    "auto approve",
    "auto-approve",
    "no approval needed",
    "does not require approval",
    "change has been made",
    "applied in amazon",
    "i have changed",
    "will change in amazon",
}


class AiRecommendationEvidence(BaseModel):
    metrics_used: dict[str, Any] = Field(default_factory=dict)
    main_signals: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AiProposedAction(BaseModel):
    action: str
    action_level: str
    suggested_bid_multiplier: Decimal | None = None
    negative_match_type: str | None = None
    requires_human_approval: bool
    executes_live_amazon_change: bool

    model_config = ConfigDict(extra="allow")


class AiRecommendationItem(BaseModel):
    entity_type: str
    recommendation_type: str
    priority: str
    confidence: str
    campaign_name: str
    ad_group_name: str | None = None
    targeting: str | None = None
    customer_search_term: str | None = None
    reasoning_summary: str
    evidence: AiRecommendationEvidence
    proposed_action: AiProposedAction

    model_config = ConfigDict(extra="forbid")


class AiDashboardSummary(BaseModel):
    headline: str
    top_winners: list[Any] = Field(default_factory=list)
    top_wasters: list[Any] = Field(default_factory=list)
    main_risks: list[Any] = Field(default_factory=list)
    next_best_actions: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AiRecommendationOutput(BaseModel):
    recommendations: list[AiRecommendationItem] = Field(default_factory=list)
    dashboard_summary: AiDashboardSummary

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class AiRecommendationBrainResult:
    recommendations: list[Recommendation]
    ai_run: AiRun
    used_ai: bool
    validation_errors: list[str]
    critic_findings: list[dict[str, Any]] = field(default_factory=list)
    rejected_by_critic: list[Recommendation] = field(default_factory=list)
    attempts: int = 1


# Default attempts: 1 initial + up to 2 retries. Retries feed the prior
# validation errors back to the model so it can correct them in-place,
# rather than failing the whole batch on the first bad JSON.
DEFAULT_MAX_ATTEMPTS = 3


class AiRecommendationBrain:
    def __init__(
        self,
        *,
        client: AiJsonClient | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._client = client or DeepSeekClient()
        self._max_attempts = max(1, max_attempts)

    def generate(
        self,
        *,
        product: ProductProfile,
        import_record: MonitoringImport,
        snapshots: list[MonitoringSnapshot],
        rollups: dict,
        data_quality_warnings: list[dict],
        baseline_recommendations: list[Recommendation] | None = None,
        agent_config: Any | None = None,
        pattern_index: dict[str, optimization_memory.PatternOutcome] | None = None,
        data_window_days: int | None = None,
    ) -> AiRecommendationBrainResult:
        payload = _brain_payload(
            product=product,
            import_record=import_record,
            snapshots=snapshots,
            rollups=rollups,
            data_quality_warnings=data_quality_warnings,
            baseline_recommendations=baseline_recommendations,
            agent_config=agent_config,
            pattern_index=pattern_index,
            data_window_days=data_window_days,
        )
        messages = _messages(payload)
        input_hash = _hash_payload({"messages": messages})

        last_error: str | None = None
        last_validation_errors: list[str] = []
        last_content: dict | None = None
        last_latency = 0
        provider = getattr(self._client, "provider", "unknown")
        model = getattr(self._client, "model", "unknown")

        for attempt in range(1, self._max_attempts + 1):
            current_messages = list(messages)
            if attempt > 1 and last_validation_errors:
                current_messages.append(_retry_user_message(last_validation_errors))

            try:
                response = self._client.complete_json(messages=current_messages)
            except AiClientError as exc:
                last_error = str(exc)
                last_validation_errors = [last_error]
                continue

            provider = response.provider
            model = response.model
            last_latency = response.latency_ms
            last_content = response.content_json

            try:
                parsed = AiRecommendationOutput.model_validate(response.content_json)
            except ValidationError as exc:
                last_error = str(exc)
                last_validation_errors = _pydantic_errors(exc)
                continue

            validation_errors = validate_ai_output(parsed, snapshots=snapshots)
            if validation_errors:
                last_validation_errors = validation_errors
                last_error = "; ".join(validation_errors[:3])
                continue

            ai_run = _ai_run(
                workspace_id=import_record.workspace_id,
                product_id=import_record.product_id,
                provider=provider,
                model=model,
                input_hash=input_hash,
                output_json={
                    **response.content_json,
                    "input_json": payload,
                    "validation_errors": [],
                    "attempts": attempt,
                },
                status="succeeded",
                latency_ms=last_latency,
            )
            recommendations = _recommendations_from_ai(
                product=product,
                import_record=import_record,
                snapshots=snapshots,
                rollups=rollups,
                ai_run=ai_run,
                output=parsed,
                pattern_index=pattern_index or {},
                data_window_days=data_window_days,
                agent_config=agent_config,
            )

            critic_outcome = ai_critic.critique(
                recommendations=recommendations,
                snapshots=snapshots,
            )
            findings_json = [f.to_json() for f in critic_outcome.findings]

            return AiRecommendationBrainResult(
                recommendations=critic_outcome.accepted,
                ai_run=ai_run,
                used_ai=True,
                validation_errors=[],
                critic_findings=findings_json,
                rejected_by_critic=critic_outcome.rejected,
                attempts=attempt,
            )

        # All attempts exhausted — record a failed ai_run with the last error.
        message = last_error or "AI recommendation generation failed after retries."
        ai_run = _ai_run(
            workspace_id=import_record.workspace_id,
            product_id=import_record.product_id,
            provider=provider,
            model=model,
            input_hash=input_hash,
            output_json={
                "error": message,
                "input_json": payload,
                "validation_errors": last_validation_errors or [message],
                "last_content_json": last_content,
                "dashboard_summary": _failed_dashboard_summary(message),
                "attempts": self._max_attempts,
            },
            status="failed",
            latency_ms=last_latency,
        )
        return AiRecommendationBrainResult(
            recommendations=[],
            ai_run=ai_run,
            used_ai=False,
            validation_errors=last_validation_errors or [message],
            attempts=self._max_attempts,
        )


def build_deterministic_recommendations(
    *,
    product: ProductProfile,
    import_record: MonitoringImport,
    snapshots: list[MonitoringSnapshot],
    decision_source: str = DETERMINISTIC_DECISION_SOURCE,
    ai_run: AiRun | None = None,
) -> list[Recommendation]:
    recommendations = build_recommendations(product=product, import_record=import_record, snapshots=snapshots)
    return apply_recommendation_source(recommendations=recommendations, decision_source=decision_source, ai_run=ai_run)


def apply_recommendation_source(*, recommendations: list[Recommendation], decision_source: str, ai_run: AiRun | None = None) -> list[Recommendation]:
    updated: list[Recommendation] = []
    for recommendation in recommendations:
        evidence = {
            **recommendation.evidence_json,
            "decision_source": decision_source,
            "ai_run_id": str(ai_run.id) if ai_run else None,
            "ai_provider": ai_run.provider if ai_run else None,
            "ai_model": ai_run.model if ai_run else None,
            "ai_schema_version": ai_run.schema_version if ai_run else None,
            "approval_boundary": {
                **recommendation.evidence_json.get("approval_boundary", {}),
                "requires_human_approval": True,
                "executes_live_amazon_change": False,
                "amazon_ads_api_mutation": False,
            },
        }
        explanation = {
            **recommendation.explanation_json,
            "decision_source": decision_source,
            "ai_run_id": str(ai_run.id) if ai_run else None,
            "ai_provider": ai_run.provider if ai_run else None,
            "ai_model": ai_run.model if ai_run else None,
            "approval_required": True,
            "ai_final_decision": decision_source == DEEPSEEK_DECISION_SOURCE,
            "execution_boundary": "recommendation_only_no_live_amazon_change",
        }
        updated.append(recommendation.model_copy(update={"evidence_json": evidence, "explanation_json": explanation}))
    return updated


def validate_ai_output(output: AiRecommendationOutput, *, snapshots: list[MonitoringSnapshot]) -> list[str]:
    errors: list[str] = []
    if not output.dashboard_summary.headline.strip():
        errors.append("dashboard_summary.headline is required.")
    if not output.recommendations:
        errors.append("At least one recommendation is required.")
    for index, item in enumerate(output.recommendations):
        prefix = f"recommendations[{index}]"
        errors.extend(_validate_enum(item.entity_type, RecommendationEntityType, f"{prefix}.entity_type"))
        errors.extend(_validate_enum(item.recommendation_type, RecommendationType, f"{prefix}.recommendation_type"))
        errors.extend(_validate_enum(item.priority, RecommendationPriority, f"{prefix}.priority"))
        errors.extend(_validate_enum(item.confidence, RecommendationConfidence, f"{prefix}.confidence"))
        if not item.reasoning_summary.strip():
            errors.append(f"{prefix}.reasoning_summary is required.")
        if not item.evidence.metrics_used and not item.evidence.main_signals:
            errors.append(f"{prefix}.evidence must include metrics_used or main_signals.")
        if item.proposed_action.requires_human_approval is not True:
            errors.append(f"{prefix}.proposed_action.requires_human_approval must be true.")
        if item.proposed_action.executes_live_amazon_change is not False:
            errors.append(f"{prefix}.proposed_action.executes_live_amazon_change must be false.")
        if item.proposed_action.action_level not in {"campaign", "ad_group", "target", "search_term"}:
            errors.append(f"{prefix}.proposed_action.action_level is invalid.")
        if item.proposed_action.suggested_bid_multiplier is not None and not (Decimal("0.5") <= item.proposed_action.suggested_bid_multiplier <= Decimal("1.5")):
            errors.append(f"{prefix}.proposed_action.suggested_bid_multiplier must be between 0.5 and 1.5.")
        if item.recommendation_type in {RecommendationType.ADD_NEGATIVE_EXACT.value, RecommendationType.ADD_NEGATIVE_PHRASE.value} and item.proposed_action.negative_match_type not in {"exact", "phrase"}:
            errors.append(f"{prefix}.proposed_action.negative_match_type is required for negative keyword recommendations.")
        if _contains_live_mutation_instruction(item.model_dump(mode="json")):
            errors.append(f"{prefix} contains direct Amazon Ads mutation or approval-bypass instructions.")
        if _matching_snapshot(item, snapshots) is None:
            errors.append(f"{prefix} does not reference an entity present in the uploaded snapshots.")
    return errors


def _recommendations_from_ai(
    *,
    product: ProductProfile,
    import_record: MonitoringImport,
    snapshots: list[MonitoringSnapshot],
    rollups: dict,
    ai_run: AiRun,
    output: AiRecommendationOutput,
    pattern_index: dict[str, optimization_memory.PatternOutcome] | None = None,
    data_window_days: int | None = None,
    agent_config: Any | None = None,
) -> list[Recommendation]:
    now = datetime.now(UTC)
    pattern_index = pattern_index or {}
    strategy_mode = _strategy_mode_from_config(agent_config)
    recommendations: list[Recommendation] = []
    for item in output.recommendations:
        snapshot = _matching_snapshot(item, snapshots)
        if snapshot is None:
            continue
        metrics = monitoring_metrics.snapshot_metrics(snapshot, report_performance=rollups["report"])
        recommendation_type = RecommendationType(item.recommendation_type)
        priority = RecommendationPriority(item.priority)
        ai_self_confidence = RecommendationConfidence(item.confidence)

        # Override the LLM's self-reported confidence with one computed from
        # evidence. Reviewers see *both*: the deterministic confidence drives
        # prioritization, and the AI's claim is kept in the audit trail.
        pattern_outcome = optimization_memory.lookup_pattern_for_candidate(
            pattern_index=pattern_index,
            snapshot=snapshot,
            action=recommendation_type.value,
            strategy_mode=strategy_mode,
            target_acos=product.target_acos,
        )
        breakdown = confidence_module.compute_confidence(
            snapshot=snapshot,
            recommendation_type=recommendation_type,
            data_window_days=data_window_days,
            pattern_outcome=pattern_outcome.to_dict() if pattern_outcome else None,
        )
        confidence = breakdown.confidence
        proposed_action = _safe_proposed_action(item, snapshot)
        recommendations.append(
            Recommendation(
                id=uuid4(),
                workspace_id=import_record.workspace_id,
                product_id=import_record.product_id,
                monitoring_import_id=import_record.id,
                snapshot_id=snapshot.id,
                recommendation_type=recommendation_type,
                entity_type=RecommendationEntityType(item.entity_type),
                status=RecommendationStatus.PENDING_APPROVAL,
                priority=priority,
                confidence=confidence,
                rule_version_id=AI_RECOMMENDATION_SCHEMA_VERSION,
                rule_name="deepseek_ai_recommendation_brain",
                campaign_name=snapshot.campaign_name,
                ad_group_name=snapshot.ad_group_name,
                targeting=snapshot.targeting,
                customer_search_term=snapshot.customer_search_term,
                input_metrics_json=metrics,
                current_metric_snapshot_json=metrics,
                evidence_json=_ai_evidence_json(
                    item=item,
                    snapshot=snapshot,
                    metrics=metrics,
                    rollups=rollups,
                    product=product,
                    ai_run=ai_run,
                ),
                proposed_action_json=proposed_action,
                explanation_json={
                    "summary": item.reasoning_summary,
                    "priority": priority.value,
                    "confidence": confidence.value,
                    "ai_self_reported_confidence": ai_self_confidence.value,
                    "confidence_breakdown": breakdown.to_json(),
                    "pattern_outcome": pattern_outcome.to_dict() if pattern_outcome else None,
                    "decision_source": DEEPSEEK_DECISION_SOURCE,
                    "ai_run_id": str(ai_run.id),
                    "ai_provider": ai_run.provider,
                    "ai_model": ai_run.model,
                    "ai_schema_version": ai_run.schema_version,
                    "approval_required": True,
                    "ai_final_decision": True,
                    "execution_boundary": "recommendation_only_no_live_amazon_change",
                    "dashboard_summary": output.dashboard_summary.model_dump(mode="json"),
                },
                created_at=now,
                updated_at=now,
            )
        )
    return recommendations


def _strategy_mode_from_config(agent_config: Any | None) -> str:
    if agent_config is None:
        return "balanced"
    data = agent_config.model_dump(mode="json") if hasattr(agent_config, "model_dump") else dict(agent_config)
    goal = data.get("optimization_goal") or data.get("mode") or "balanced"
    return str(goal)


def _retry_user_message(validation_errors: list[str]) -> dict[str, str]:
    """Build a follow-up user message that feeds validation errors back to the
    model. We cap at 8 errors and tell the model exactly what to fix; the
    response must be a full corrected output, not a diff."""

    capped = validation_errors[:8]
    body = {
        "task": "retry_after_validation_failure",
        "instruction": (
            "Your previous response failed validation. "
            "Produce a corrected JSON output that satisfies the schema and all stated rules. "
            "Do not change any deterministic metric values. "
            "Keep requires_human_approval true and executes_live_amazon_change false on every action."
        ),
        "validation_errors": capped,
    }
    return {"role": "user", "content": json.dumps(body, sort_keys=True)}


def _pydantic_errors(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = err.get("msg", "validation error")
        out.append(f"{loc}: {msg}" if loc else msg)
    return out[:10]


def _brain_payload(
    *,
    product: ProductProfile,
    import_record: MonitoringImport,
    snapshots: list[MonitoringSnapshot],
    rollups: dict,
    data_quality_warnings: list[dict],
    baseline_recommendations: list[Recommendation] | None,
    agent_config: Any | None,
    pattern_index: dict[str, optimization_memory.PatternOutcome] | None = None,
    data_window_days: int | None = None,
) -> dict:
    return {
        "report_context": {
            "report_type": import_record.report_type,
            "scope": "single_product_report",
            "row_count": len(snapshots),
            "date_range": {"start": import_record.date_range_start, "end": import_record.date_range_end},
            "detected_products": [
                {
                    "product_id": str(product.id),
                    "product_name": product.product_name,
                    "asin": product.asin,
                    "sku": product.sku,
                    "marketplace": product.marketplace,
                    "currency": product.currency,
                }
            ],
        },
        "agent_config": _agent_config_payload(agent_config),
        "grouped_metrics": {
            "account": rollups.get("report", {}),
            "products": [
                {
                    "product_id": str(product.id),
                    "product_name": product.product_name,
                    "target_acos": str(product.target_acos),
                    "default_bid": str(product.default_bid),
                    "default_budget": str(product.default_budget),
                    "metrics": rollups.get("report", {}),
                }
            ],
            "campaigns": _rollup_items(rollups.get("campaign", {})),
            "ad_groups": _rollup_items(rollups.get("ad_group", {})),
            "targets": _rollup_items(rollups.get("target", {})),
            "search_terms": _rollup_items(rollups.get("search_term", {})),
        },
        "monitoring_import": {
            "id": str(import_record.id),
            "report_type": import_record.report_type,
            "upload_id": str(import_record.upload_id),
            "parse_run_id": str(import_record.parse_run_id),
        },
        "snapshots": [_snapshot_payload(snapshot, rollups, product) for snapshot in snapshots],
        "rollups": rollups,
        "data_quality_warnings": data_quality_warnings,
        "baseline_recommendations": [_baseline_payload(item) for item in (baseline_recommendations or [])],
        "candidate_actions": [_candidate_payload(item) for item in (baseline_recommendations or [])],
        "prior_pattern_outcomes": _pattern_outcomes_payload(pattern_index, baseline_recommendations or []),
        "data_window_days": data_window_days,
        "your_job": (
            "Select, rank, group, and explain among the candidate_actions above. "
            "You may also add new recommendations only if the snapshots clearly support them. "
            "Do not recalculate metrics. Prioritize evidence strength, strategic alignment, and impact."
        ),
        "safety_boundaries": {
            "ai_may_generate_recommendation_decisions": True,
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
            "amazon_ads_api_mutation_allowed": False,
            "approval_or_rejection_allowed_for_ai": False,
            "metrics_are_deterministic_inputs": True,
        },
        "output_schema_version": AI_RECOMMENDATION_SCHEMA_VERSION,
    }


def _agent_config_payload(agent_config: Any | None) -> dict:
    if agent_config is None:
        return {
            "strictness_level": "balanced",
            "confidence_threshold": "medium",
            "analysis_depth": "standard",
            "allowed_recommendation_types": [],
            "risk_controls": {},
        }
    data = agent_config.model_dump(mode="json") if hasattr(agent_config, "model_dump") else dict(agent_config)
    return {
        "enabled": data.get("enabled", True),
        "mode": data.get("mode", "hybrid"),
        "provider": data.get("provider", "deepseek"),
        "model": data.get("model"),
        "strictness_level": data.get("strictness_level", "balanced"),
        "confidence_threshold": data.get("confidence_threshold", "medium"),
        "max_recommendations": data.get("max_recommendations"),
        "max_rows_per_ai_call": data.get("max_rows_per_ai_call"),
        "max_products_per_run": data.get("max_products_per_run"),
        "analysis_depth": data.get("analysis_depth", "standard"),
        "include_account_level_analysis": data.get("include_account_level_analysis", True),
        "include_product_level_analysis": data.get("include_product_level_analysis", True),
        "include_campaign_level_analysis": data.get("include_campaign_level_analysis", True),
        "include_keyword_level_analysis": data.get("include_keyword_level_analysis", True),
        "include_search_term_level_analysis": data.get("include_search_term_level_analysis", True),
        "allowed_recommendation_types": [
            name.removeprefix("allow_")
            for name in [
                "allow_keep_running",
                "allow_increase_bid",
                "allow_decrease_bid",
                "allow_pause_review",
                "allow_negative_exact",
                "allow_negative_phrase",
                "allow_move_to_exact",
                "allow_budget_review",
                "allow_data_quality_review",
                "allow_product_mapping_recommendations",
            ]
            if data.get(name, True)
        ],
        "risk_controls": {
            "max_bid_increase_multiplier": data.get("max_bid_increase_multiplier"),
            "max_bid_decrease_multiplier": data.get("max_bid_decrease_multiplier"),
            "require_high_confidence_for_pause": data.get("require_high_confidence_for_pause"),
            "require_high_confidence_for_negative_keywords": data.get("require_high_confidence_for_negative_keywords"),
            "require_min_clicks_before_action": data.get("require_min_clicks_before_action"),
            "require_min_spend_before_action": data.get("require_min_spend_before_action"),
            "target_acos_override": data.get("target_acos_override"),
            "min_orders_for_scaling": data.get("min_orders_for_scaling"),
            "min_roas_for_scaling": data.get("min_roas_for_scaling"),
        },
        "optimization_goal": data.get("optimization_goal"),
        "custom_business_goal": data.get("custom_business_goal"),
        "brand_safety_notes": data.get("brand_safety_notes"),
        "competitor_notes": data.get("competitor_notes"),
        "product_margin_notes": data.get("product_margin_notes"),
        "output_controls": {
            "recommendation_language": data.get("recommendation_language"),
            "explanation_detail": data.get("explanation_detail"),
            "show_raw_ai_reasoning_summary": data.get("show_raw_ai_reasoning_summary"),
            "show_metric_evidence": data.get("show_metric_evidence"),
            "require_action_risk_note": data.get("require_action_risk_note"),
        },
        "chunking": {
            "max_groups_per_ai_call": data.get("max_groups_per_ai_call"),
            "chunk_strategy": data.get("chunk_strategy"),
        },
    }


def _rollup_items(rollups: dict) -> list[dict]:
    return [{"entity_key": key, "metrics": value} for key, value in rollups.items()]


def _messages(payload: dict) -> list[dict[str, str]]:
    system = (
        "You are the recommendation brain for an Amazon Ads SaaS monitoring workflow. "
        "The backend has already pre-computed all metrics and a list of deterministic candidate_actions. "
        "Your primary job is to SELECT, RANK, GROUP, and EXPLAIN among those candidates — not to invent new ones from raw rows. "
        "You may add a recommendation outside the candidate list only when the snapshots clearly support it. "
        "Return JSON only. Do not recalculate metrics. Do not approve, reject, execute, export, or call Amazon Ads APIs. "
        "Do not claim a live Amazon change was made. "
        "Every proposed_action.requires_human_approval must be true and executes_live_amazon_change must be false. "
        "Your self-reported confidence is advisory only — the backend recomputes confidence from evidence."
    )
    user = {
        "task": "Analyze uploaded Sponsored Products Search Term report evidence and produce recommendation JSON only.",
        "allowed_entity_type": [item.value for item in RecommendationEntityType],
        "allowed_recommendation_type": [item.value for item in RecommendationType if item != RecommendationType.LEGACY_NEGATIVE_KEYWORD_REVIEW],
        "allowed_priority": [item.value for item in RecommendationPriority],
        "allowed_confidence": [item.value for item in RecommendationConfidence],
        "required_output_shape": {
            "recommendations": [
                {
                    "entity_type": "campaign | ad_group | target | search_term",
                    "recommendation_type": "keep_running | increase_bid | decrease_bid | pause_review | add_negative_exact | add_negative_phrase | move_to_exact | watch_lock | data_quality_review | budget_review",
                    "priority": "critical | high | medium | low",
                    "confidence": "high | medium | low",
                    "campaign_name": "...",
                    "ad_group_name": "...",
                    "targeting": "...",
                    "customer_search_term": "...",
                    "reasoning_summary": "...",
                    "evidence": {"metrics_used": {}, "main_signals": [], "risk_factors": [], "data_limitations": []},
                    "proposed_action": {
                        "action": "...",
                        "action_level": "campaign | ad_group | target | search_term",
                        "suggested_bid_multiplier": None,
                        "negative_match_type": None,
                        "requires_human_approval": True,
                        "executes_live_amazon_change": False,
                    },
                }
            ],
            "dashboard_summary": {"headline": "...", "top_winners": [], "top_wasters": [], "main_risks": [], "next_best_actions": []},
        },
        "input": payload,
    }
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)}]


def _snapshot_payload(snapshot: MonitoringSnapshot, rollups: dict, product: ProductProfile) -> dict:
    metrics = monitoring_metrics.snapshot_metrics(snapshot, report_performance=rollups["report"])
    return {
        "snapshot_id": str(snapshot.id),
        "campaign_name": snapshot.campaign_name,
        "ad_group_name": snapshot.ad_group_name,
        "targeting": snapshot.targeting,
        "match_type": snapshot.match_type,
        "customer_search_term": snapshot.customer_search_term,
        "start_date": snapshot.start_date,
        "end_date": snapshot.end_date,
        "metrics": metrics,
        "condition_signals": monitoring_metrics.condition_signals(snapshot, target_acos=product.target_acos, default_budget=product.default_budget, report_performance=rollups["report"]),
        "rollup_keys": {
            "campaign": monitoring_metrics.campaign_key(snapshot),
            "ad_group": monitoring_metrics.ad_group_key(snapshot),
            "target": monitoring_metrics.target_key(snapshot),
            "search_term": monitoring_metrics.search_term_key(snapshot),
        },
    }


def _baseline_payload(recommendation: Recommendation) -> dict:
    return {
        "recommendation_type": recommendation.recommendation_type.value,
        "entity_type": recommendation.entity_type.value,
        "priority": recommendation.priority.value,
        "confidence": recommendation.confidence.value,
        "campaign_name": recommendation.campaign_name,
        "ad_group_name": recommendation.ad_group_name,
        "targeting": recommendation.targeting,
        "customer_search_term": recommendation.customer_search_term,
        "metrics": recommendation.current_metric_snapshot_json or recommendation.input_metrics_json,
        "proposed_action": recommendation.proposed_action_json,
    }


def _candidate_payload(recommendation: Recommendation) -> dict:
    """A compact view of a deterministic candidate, for the prompt's
    candidate_actions section. The brain reads these to pick winners."""

    return {
        "candidate_id": str(recommendation.id),
        "action": recommendation.recommendation_type.value,
        "entity_type": recommendation.entity_type.value,
        "campaign_name": recommendation.campaign_name,
        "ad_group_name": recommendation.ad_group_name,
        "targeting": recommendation.targeting,
        "customer_search_term": recommendation.customer_search_term,
        "deterministic_priority": recommendation.priority.value,
        "deterministic_evidence_score": (
            recommendation.evidence_score.score
            if recommendation.evidence_score is not None
            else None
        ),
        "rule_name": recommendation.rule_name,
    }


def _pattern_outcomes_payload(
    pattern_index: dict[str, optimization_memory.PatternOutcome] | None,
    baseline_recommendations: list[Recommendation],
) -> list[dict]:
    """Surface only the patterns that intersect candidates in this run.

    Sending the entire pattern_index would dominate the prompt for big
    accounts; we narrow to the actions actually under consideration.
    """

    if not pattern_index:
        return []

    candidate_actions = {rec.recommendation_type.value for rec in baseline_recommendations}
    out: list[dict] = []
    for key_str, outcome in pattern_index.items():
        if outcome.key.action in candidate_actions or not candidate_actions:
            out.append(outcome.to_dict())
    return out


def _ai_evidence_json(*, item: AiRecommendationItem, snapshot: MonitoringSnapshot, metrics: dict, rollups: dict, product: ProductProfile, ai_run: AiRun) -> dict:
    return {
        "schema_version": MONITORING_EVIDENCE_SCHEMA_VERSION,
        "ai_schema_version": AI_RECOMMENDATION_SCHEMA_VERSION,
        "decision_source": DEEPSEEK_DECISION_SOURCE,
        "ai_run_id": str(ai_run.id),
        "ai_provider": ai_run.provider,
        "ai_model": ai_run.model,
        "ai_reasoning_summary": item.reasoning_summary,
        "ai_evidence": item.evidence.model_dump(mode="json"),
        "product_settings": {
            "target_acos": str(product.target_acos),
            "default_bid": str(product.default_bid),
            "default_budget": str(product.default_budget),
            "marketplace": product.marketplace,
            "currency": product.currency,
        },
        "snapshot_metrics": metrics,
        "search_term_performance": rollups["search_term"][monitoring_metrics.search_term_key(snapshot)],
        "target_performance": rollups["target"][monitoring_metrics.target_key(snapshot)],
        "ad_group_performance": rollups["ad_group"][monitoring_metrics.ad_group_key(snapshot)],
        "campaign_performance": rollups["campaign"][snapshot.campaign_name],
        "report_performance": rollups["report"],
        "approval_boundary": {
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
            "amazon_ads_api_mutation": False,
            "approval_only_updates_app_state_and_audit": True,
        },
    }


def _safe_proposed_action(item: AiRecommendationItem, snapshot: MonitoringSnapshot) -> dict:
    action = item.proposed_action.model_dump(mode="json")
    return {
        **action,
        "campaign_name": snapshot.campaign_name,
        "ad_group_name": snapshot.ad_group_name,
        "targeting": snapshot.targeting,
        "customer_search_term": snapshot.customer_search_term,
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
        "amazon_ads_api_mutation": False,
    }


def _matching_snapshot(item: AiRecommendationItem, snapshots: list[MonitoringSnapshot]) -> MonitoringSnapshot | None:
    entity_type = item.entity_type
    campaign = _norm(item.campaign_name)
    ad_group = _norm(item.ad_group_name)
    targeting = _norm(item.targeting)
    search_term = _norm(item.customer_search_term)
    for snapshot in snapshots:
        if _norm(snapshot.campaign_name) != campaign:
            continue
        if entity_type == RecommendationEntityType.CAMPAIGN.value:
            return snapshot
        if _norm(snapshot.ad_group_name) != ad_group:
            continue
        if entity_type == RecommendationEntityType.AD_GROUP.value:
            return snapshot
        if _norm(snapshot.targeting) != targeting:
            continue
        if entity_type == RecommendationEntityType.TARGET.value:
            return snapshot
        if _norm(snapshot.customer_search_term) == search_term:
            return snapshot
    return None


def _validate_enum(value: str, enum_class, field: str) -> list[str]:
    try:
        enum_class(value)
        if enum_class is RecommendationType and value == RecommendationType.LEGACY_NEGATIVE_KEYWORD_REVIEW.value:
            return [f"{field} is not allowed for AI recommendations."]
        return []
    except ValueError:
        return [f"{field} is invalid."]


def _contains_live_mutation_instruction(value: dict) -> bool:
    haystack = json.dumps(value, sort_keys=True).lower()
    return any(phrase in haystack for phrase in _LIVE_MUTATION_PHRASES)


def _failed_dashboard_summary(message: str) -> dict:
    return {
        "headline": "AI recommendation generation failed validation or provider checks.",
        "top_winners": [],
        "top_wasters": [],
        "main_risks": [message],
        "next_best_actions": ["Review data quality and retry AI analysis or use deterministic fallback mode."],
    }


def _ai_run(
    *,
    workspace_id: UUID,
    product_id: UUID,
    provider: str,
    model: str,
    input_hash: str,
    output_json: dict,
    status: str,
    latency_ms: int,
) -> AiRun:
    return AiRun(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        agent_name=AI_RECOMMENDATION_AGENT_NAME,
        provider=provider,
        model=model,
        schema_version=AI_RECOMMENDATION_SCHEMA_VERSION,
        input_hash=input_hash,
        output_json=output_json,
        status=status,
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )


def _hash_payload(payload: dict) -> str:
    return sha256(json.dumps(payload, default=str, sort_keys=True).encode("utf-8")).hexdigest()


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()
