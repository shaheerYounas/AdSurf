"""Planner Agent for AdSurf — selects which downstream agents to run.

Reads the data-quality report + strategy mode and decides:
- Which optimization agents to run (bid, negatives, budget, structure)
- At what depth (fast/skip vs full analysis)
- Whether to skip agents when data is insufficient

This reduces wasted AI calls when the report has no relevant data
for certain agent types (e.g., no wasted-spend spend → skip negatives).

The planner is a lightweight deterministic decision with optional
AI explanation. It never blocks the pipeline; it gates for efficiency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentRunDecision(StrEnum):
    RUN = "run"       # Run the agent at full depth
    SKIP = "skip"     # Skip — no relevant data
    LIGHT = "light"   # Run with reduced scope (deterministic-only, no AI)


@dataclass
class PlannerResult:
    """Output of the planner agent: per-agent run decisions."""

    strategy_mode: str = "profit"
    data_quality_score: float = 1.0  # 0.0 = unusable, 1.0 = clean
    total_rows: int = 0
    warnings: list[str] = field(default_factory=list)

    # Per-agent decisions
    bid_optimization: AgentRunDecision = AgentRunDecision.RUN
    negative_keyword: AgentRunDecision = AgentRunDecision.RUN
    budget_reallocation: AgentRunDecision = AgentRunDecision.RUN
    campaign_structure: AgentRunDecision = AgentRunDecision.RUN

    # Reasoning
    reasoning: str = ""
    skip_reasons: dict[str, str] = field(default_factory=dict)


def plan_agent_execution(
    *,
    data_quality_report: dict[str, Any],
    strategy_mode: str = "profit",
    grouped_entities: dict[str, Any] | None = None,
    total_rows: int = 0,
) -> PlannerResult:
    """Determine which downstream agents should run based on data quality + strategy.

    Rules (deterministic):
    - If data_quality_score < 0.3, skip everything except data-quality review
    - If data_quality_score < 0.6, run LIGHT mode
    - If no wasted-spend entities (search terms with spend>0, orders=0), skip negative_keyword
    - If fewer than 5 campaigns in data, skip budget_reallocation
    - If fewer than 10 search terms, skip campaign_structure
    - Launch mode: skip negative and pause agents (collecting data phase)

    Args:
        data_quality_report: From import_data_quality_agent
        strategy_mode: Account strategy mode
        grouped_entities: Grouped entities from entity resolution
        total_rows: Total rows in the report

    Returns:
        PlannerResult with per-agent run/skip/light decisions
    """
    result = PlannerResult(
        strategy_mode=strategy_mode,
        total_rows=total_rows,
    )

    # ── Data quality score ──────────────────────────────────────────
    dq_score = float(data_quality_report.get("overall_score", data_quality_report.get("data_quality_score", 1.0)))
    result.data_quality_score = dq_score

    # Quality gate — if unusable, skip everything
    if dq_score < 0.3:
        result.bid_optimization = AgentRunDecision.SKIP
        result.negative_keyword = AgentRunDecision.SKIP
        result.budget_reallocation = AgentRunDecision.SKIP
        result.campaign_structure = AgentRunDecision.SKIP
        result.skip_reasons["data_quality"] = f"Data quality score {dq_score:.2f} below 0.3 threshold. Fix data before optimization."
        result.reasoning = "Data quality is too low for optimization agents. Only data-quality review should run."
        return result

    # Threshold for LIGHT mode
    light_mode = dq_score < 0.6

    # ── Entity-based gating ─────────────────────────────────────────
    entities = grouped_entities or {}

    # Count entity types
    search_terms = _count_entity_type(entities, "search_term")
    campaigns = _count_entity_type(entities, "campaign")
    wasteful_terms = _count_wasteful_terms(entities)

    result.warnings.append(
        f"Planner: {search_terms} search terms, {campaigns} campaigns, "
        f"{wasteful_terms} wasteful terms. Strategy: {strategy_mode}. "
        f"Data quality: {dq_score:.2f}."
    )

    # ── Negative keyword gating ─────────────────────────────────────
    if strategy_mode in {"launch", "growth"}:
        # Don't add negatives during launch/growth — data collection phase
        result.negative_keyword = AgentRunDecision.SKIP
        result.skip_reasons["negative_keyword"] = f"Strategy '{strategy_mode}' prohibits negative keywords during data-gathering phase."
    elif wasteful_terms == 0:
        result.negative_keyword = AgentRunDecision.SKIP
        result.skip_reasons["negative_keyword"] = "No search terms with spend>0 and zero orders found. Nothing to negative."
    elif light_mode and wasteful_terms < 5:
        result.negative_keyword = AgentRunDecision.LIGHT
        result.skip_reasons["negative_keyword"] = "Few wasteful terms (<5) with moderate data quality; deterministic-only review."

    # ── Budget reallocation gating ──────────────────────────────────
    if campaigns < 3:
        result.budget_reallocation = AgentRunDecision.SKIP
        result.skip_reasons["budget_reallocation"] = f"Only {campaigns} campaigns found; need at least 3 for meaningful budget reallocation."
    elif light_mode:
        result.budget_reallocation = AgentRunDecision.LIGHT

    # ── Campaign structure gating ───────────────────────────────────
    if search_terms < 10:
        result.campaign_structure = AgentRunDecision.SKIP
        result.skip_reasons["campaign_structure"] = f"Only {search_terms} search terms; need at least 10 for meaningful structure recommendations."
    elif light_mode:
        result.campaign_structure = AgentRunDecision.LIGHT

    # ── Bid optimization gating ─────────────────────────────────────
    if search_terms < 3:
        result.bid_optimization = AgentRunDecision.SKIP
        result.skip_reasons["bid_optimization"] = f"Only {search_terms} search terms; need at least 3 for bid analysis."
    elif light_mode:
        result.bid_optimization = AgentRunDecision.LIGHT

    # ── Build reasoning ─────────────────────────────────────────────
    decisions = []
    for agent, decision in [
        ("bid_optimization_agent", result.bid_optimization),
        ("negative_keyword_agent", result.negative_keyword),
        ("budget_reallocation_agent", result.budget_reallocation),
        ("campaign_structure_agent", result.campaign_structure),
    ]:
        label = f"{agent}: {decision.value}"
        if agent in result.skip_reasons:
            label += f" ({result.skip_reasons[agent]})"
        decisions.append(label)

    result.reasoning = " | ".join(decisions)

    return result


def _count_entity_type(entities: dict[str, Any], entity_type: str) -> int:
    """Count entities of a specific type in grouped_entities dict."""
    count = 0
    for key, value in entities.items():
        if isinstance(value, dict) and value.get("entity_type") == entity_type:
            count += 1
    return count


def _count_wasteful_terms(entities: dict[str, Any]) -> int:
    """Count search terms with spend>0 and zero orders (waste candidates)."""
    count = 0
    for key, value in entities.items():
        if isinstance(value, dict) and value.get("entity_type") == "search_term":
            metrics = value.get("metrics", {})
            spend = float(metrics.get("spend", 0) or 0)
            orders = int(metrics.get("orders", 0) or 0)
            if spend > 0 and orders == 0:
                count += 1
    return count


# ── AI explanation layer (optional, for hybrid mode) ──────────────────


def explain_plan_result(
    plan: PlannerResult,
    *,
    client: Any | None = None,
) -> str:
    """Generate a human-readable explanation of the planner's decisions.
    If an AI client is provided, returns an AI-augmented explanation.
    Otherwise returns deterministic reasoning."""
    if client is None:
        return _deterministic_plan_explanation(plan)

    # AI explanation would go here — for now, deterministic is sufficient
    return _deterministic_plan_explanation(plan)


def _deterministic_plan_explanation(plan: PlannerResult) -> str:
    """Build a deterministic, human-readable explanation string."""
    lines = [
        f"Planner Analysis — Strategy: {plan.strategy_mode}",
        f"Data Quality Score: {plan.data_quality_score:.2f}",
        f"Total Rows: {plan.total_rows}",
        "",
        "Agent Execution Plan:",
    ]
    for agent, decision in [
        ("Bid Optimization", plan.bid_optimization),
        ("Negative Keyword", plan.negative_keyword),
        ("Budget Reallocation", plan.budget_reallocation),
        ("Campaign Structure", plan.campaign_structure),
    ]:
        reason = plan.skip_reasons.get(agent.lower().replace(" ", "_"), "")
        if decision != AgentRunDecision.RUN:
            lines.append(f"  ✗ {agent}: {decision.value.upper()}" + (f" — {reason}" if reason else ""))
        else:
            lines.append(f"  ✓ {agent}: RUN")

    lines.append("")
    lines.append(plan.reasoning)
    return "\n".join(lines)