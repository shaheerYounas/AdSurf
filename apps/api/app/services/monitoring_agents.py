from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID, uuid4

from apps.api.app.domain.monitoring import AGENT_SCHEMA_VERSION
from apps.api.app.schemas.monitoring import AiRun, MonitoringImport, MonitoringSnapshot, Recommendation
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet


AGENT_MODEL = "deterministic-agent-explainer-v1"
AGENT_PROVIDER = "local-deterministic-explainer"


def build_monitoring_agent_runs(
    *,
    workspace_id: UUID,
    product_id: UUID,
    import_record: MonitoringImport,
    recommendations: list[Recommendation],
    snapshots: list[MonitoringSnapshot],
    warnings: list[dict],
) -> list[AiRun]:
    quality = _quality_summary(import_record=import_record, snapshots=snapshots, warnings=warnings)
    performance = _performance_summary(recommendations=recommendations, snapshots=snapshots)
    bid_recs = [item for item in recommendations if item.recommendation_type in {"increase_bid", "decrease_bid", "watch_lock", "budget_review"}]
    negative_recs = [item for item in recommendations if item.recommendation_type in {"add_negative_exact", "add_negative_phrase"}]
    pause_recs = [item for item in recommendations if item.recommendation_type == "pause_review"]
    stakeholder = _stakeholder_summary(recommendations=recommendations, snapshots=snapshots)
    return [
        _run(workspace_id, product_id, "performance_import_agent", quality),
        _run(workspace_id, product_id, "metrics_analysis_agent", performance),
        _run(workspace_id, product_id, "bid_optimization_agent", _recommendation_explanations(bid_recs, "bid")),
        _run(workspace_id, product_id, "negative_keyword_agent", _recommendation_explanations(negative_recs, "negative_keyword")),
        _run(workspace_id, product_id, "pause_review_agent", _recommendation_explanations(pause_recs, "pause_review")),
        _run(workspace_id, product_id, "stakeholder_reporting_agent", stakeholder),
    ]


def build_failed_import_agent_run(*, workspace_id: UUID, product_id: UUID, import_record: MonitoringImport, error_code: str, message: str, details: dict) -> AiRun:
    output = {
        "report_quality_summary": message,
        "missing_columns": details.get("missing_columns", []),
        "warnings": [{"code": error_code, "message": message, "details": details}],
        "can_generate_recommendations": False,
        "refusal_boundary": _refusal_boundary(),
    }
    run = _run(workspace_id, product_id, "performance_import_agent", output)
    return run.model_copy(update={"status": "failed" if details.get("missing_columns") else "deferred"})


def _quality_summary(*, import_record: MonitoringImport, snapshots: list[MonitoringSnapshot], warnings: list[dict]) -> dict:
    return {
        "report_quality_summary": f"{len(snapshots)} rows normalized for monitoring import {import_record.id}.",
        "missing_columns": [],
        "warnings": warnings,
        "can_generate_recommendations": not warnings and bool(snapshots),
        "refusal_boundary": _refusal_boundary(),
    }


def _performance_summary(*, recommendations: list[Recommendation], snapshots: list[MonitoringSnapshot]) -> dict:
    winners = sorted([item for item in recommendations if item.recommendation_type in {"move_to_exact", "increase_bid", "budget_review"}], key=lambda item: Decimal(str(item.input_metrics_json.get("sales") or "0")), reverse=True)
    wasters = sorted([item for item in recommendations if item.recommendation_type in {"add_negative_exact", "add_negative_phrase", "pause_review"}], key=lambda item: Decimal(str(item.input_metrics_json.get("spend") or "0")), reverse=True)
    total_spend = sum((snapshot.spend for snapshot in snapshots), Decimal("0"))
    total_sales = sum((snapshot.sales for snapshot in snapshots), Decimal("0"))
    return {
        "performance_summary": f"Imported performance totals: spend {total_spend}, sales {total_sales}, recommendations {len(recommendations)}.",
        "top_winners": [_compact_recommendation(item) for item in winners[:5]],
        "top_wasters": [_compact_recommendation(item) for item in wasters[:5]],
        "risk_areas": _counts_by_type(recommendations),
        "data_limitations": ["Recommendations are based only on uploaded report rows and do not inspect live Amazon Ads state."],
        "refusal_boundary": _refusal_boundary(),
    }


def _recommendation_explanations(recommendations: list[Recommendation], category: str) -> dict:
    return {
        "category": category,
        "recommendation_count": len(recommendations),
        "items": [
            {
                **_compact_recommendation(item),
                "explanation": item.explanation_json.get("summary"),
                "why_now": item.rule_name,
                "expected_effect": _expected_effect(item.recommendation_type),
                "risk_note": "Human approval is required. This does not change Amazon Ads.",
                "confidence_reason": f"Rule confidence is {item.confidence.value} based on uploaded metric evidence.",
            }
            for item in recommendations[:25]
        ],
        "refusal_boundary": _refusal_boundary(),
    }


def _stakeholder_summary(*, recommendations: list[Recommendation], snapshots: list[MonitoringSnapshot]) -> dict:
    counts = _counts_by_type(recommendations)
    pending = sum(1 for item in recommendations if item.status == "pending_approval")
    total_spend = sum((snapshot.spend for snapshot in snapshots), Decimal("0"))
    total_sales = sum((snapshot.sales for snapshot in snapshots), Decimal("0"))
    return {
        "headline": f"{pending} recommendations need human review before any Amazon Ads change.",
        "dashboard_summary": f"{pending} recommendations are pending approval from uploaded Amazon Ads report data.",
        "executive_summary": f"Spend {total_spend}, sales {total_sales}, with no live Amazon Ads changes executed.",
        "analyst_notes": ["Review high and critical priority items first.", "Inspect data-quality recommendations before optimization decisions."],
        "approver_notes": ["Approval records an app decision only.", "Manual Amazon Console or later approved export workflow remains separate."],
        "next_best_actions": ["Review critical waste/data-quality items.", "Approve or reject each recommendation with notes."],
        "next_step": "Review critical and high priority recommendations, then approve or reject with notes.",
        "recommendation_counts": counts,
        "total_spend": str(total_spend),
        "total_sales": str(total_sales),
        "total_orders": sum(snapshot.orders for snapshot in snapshots),
        "stakeholder_note": "No AI final decision, bid change, pause, negative keyword, export, or Amazon Ads mutation has been executed.",
        "refusal_boundary": _refusal_boundary(),
    }


def _run(workspace_id: UUID, product_id: UUID, agent_name: str, output: dict) -> AiRun:
    payload = json.dumps(output, sort_keys=True, default=str)
    return AiRun(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        agent_name=agent_name,
        provider=AGENT_PROVIDER,
        model=AGENT_MODEL,
        schema_version=AGENT_SCHEMA_VERSION,
        input_hash=sha256(payload.encode("utf-8")).hexdigest(),
        output_json=output,
        status="succeeded",
        latency_ms=0,
        created_at=datetime.now(UTC),
    )


def _compact_recommendation(recommendation: Recommendation) -> dict:
    return {
        "id": str(recommendation.id),
        "type": recommendation.recommendation_type.value,
        "priority": recommendation.priority.value,
        "confidence": recommendation.confidence.value,
        "campaign_name": recommendation.campaign_name,
        "ad_group_name": recommendation.ad_group_name,
        "targeting": recommendation.targeting,
        "customer_search_term": recommendation.customer_search_term,
        "metrics": recommendation.current_metric_snapshot_json or recommendation.input_metrics_json,
    }


def _counts_by_type(recommendations: list[Recommendation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for recommendation in recommendations:
        counts[recommendation.recommendation_type.value] = counts.get(recommendation.recommendation_type.value, 0) + 1
    return counts


def _expected_effect(recommendation_type) -> str:
    mapping = {
        "increase_bid": "May improve traffic or scaling if manually applied after review.",
        "decrease_bid": "May reduce inefficient spend if manually applied after review.",
        "watch_lock": "Avoids premature action while data matures.",
        "budget_review": "Highlights scaling or budget pressure for human review.",
        "add_negative_exact": "May reduce repeated exact search-term waste if manually added.",
        "add_negative_phrase": "May reduce broad pattern waste if manually added.",
        "pause_review": "Surfaces entities that may need manual pause review.",
    }
    return mapping.get(str(recommendation_type), "Keeps the recommendation in review without live execution.")


def _refusal_boundary() -> dict:
    return {
        "requires_workspace_scope": True,
        "requires_product_scope": True,
        "requires_recommendation_evidence": True,
        "can_bypass_human_approval": False,
        "can_mutate_live_amazon_ads": False,
    }


# =============================================================================
# Dual-Path Monitoring Agent Runs: Deterministic + AI
# =============================================================================

MONITORING_AGENTS_AI_AGENT_ID = "monitoring_agents_explainer"


class DualPathMonitoringAgentsExplain(DualPathDecisionService[dict]):
    """Dual-path monitoring agents explanation service.

    Deterministic path: build_monitoring_agent_runs (exact structured summaries).
    AI path: LLM generates enhanced natural-language explanations for monitoring outputs.
    Both paths produce the same output schema (agent run output dicts).
    """

    AGENT_ID = MONITORING_AGENTS_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Monitoring Agents Explainer"

    def _deterministic_path(self, inputs: dict) -> dict:
        """Run deterministic agent run summaries."""
        recommendations: list[Recommendation] = inputs["recommendations"]
        snapshots: list[MonitoringSnapshot] = inputs["snapshots"]
        warnings: list[dict] = inputs.get("warnings", [])
        import_record: MonitoringImport = inputs["import_record"]

        return {
            "quality": _quality_summary(import_record=import_record, snapshots=snapshots, warnings=warnings),
            "performance": _performance_summary(recommendations=recommendations, snapshots=snapshots),
            "stakeholder": _stakeholder_summary(recommendations=recommendations, snapshots=snapshots),
            "decision_source": "deterministic",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        recommendations: list[Recommendation] = inputs["recommendations"]
        snapshots: list[MonitoringSnapshot] = inputs["snapshots"]
        recs_for_prompt = [
            {
                "type": r.recommendation_type.value,
                "priority": r.priority.value,
                "confidence": r.confidence.value,
                "campaign_name": r.campaign_name,
                "customer_search_term": r.customer_search_term,
                "explanation_summary": r.explanation_json.get("summary"),
            }
            for r in recommendations[:50]
        ]
        total_spend = sum((s.spend for s in snapshots), Decimal("0"))
        total_sales = sum((s.sales for s in snapshots), Decimal("0"))

        system = (
            "You are the AdSurf Monitoring Agents Explainer. "
            "Your job is to generate human-readable explanations for Amazon Ads monitoring outputs. "
            f"{safety_prompt_snippet()}"
            "You generate explanations only — you do not approve, reject, or execute any ad changes. "
            "Return JSON only. "
            "Every output must include decision_source='ai' and requires_human_approval=true."
        )
        user = {
            "task": "explain_monitoring_outputs",
            "metrics_summary": {
                "total_spend": str(total_spend),
                "total_sales": str(total_sales),
                "total_orders": sum(s.orders for s in snapshots),
                "snapshot_count": len(snapshots),
                "recommendation_count": len(recommendations),
            },
            "recommendations": recs_for_prompt,
            "required_output_shape": {
                "quality_summary": {"summary": "string", "can_generate_recommendations": "boolean"},
                "performance_summary": {"summary": "string", "top_insights": ["list of key insights"]},
                "stakeholder_summary": {"headline": "string", "next_steps": ["list of recommended next steps"]},
                "decision_source": "ai",
                "requires_human_approval": True,
                "executes_live_amazon_change": False,
            },
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)},
        ]

    def _validate_ai_output(self, ai_json: dict, inputs: dict) -> list[str]:
        errors: list[str] = []
        if ai_json.get("decision_source") != "ai":
            errors.append("decision_source must be 'ai'.")
        if ai_json.get("requires_human_approval") is not True:
            errors.append("requires_human_approval must be true.")
        if ai_json.get("executes_live_amazon_change") is not False:
            errors.append("executes_live_amazon_change must be false.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> dict:
        return {
            "quality": ai_json.get("quality_summary", {}),
            "performance": ai_json.get("performance_summary", {}),
            "stakeholder": ai_json.get("stakeholder_summary", {}),
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _empty_result(self) -> dict:
        return {
            "quality": {},
            "performance": {},
            "stakeholder": {},
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }
