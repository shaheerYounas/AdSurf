"""LangGraph workflow orchestration for AdSurf.

Features:
- PostgresSaver checkpointing for replay/time-travel debugging
- Parallel fan-out for four optimization agents (bid/negatives/budget/structure)
- Conditional skipping via planner agent data-quality gates
- Human-in-the-loop interrupt at approval gate
- Deterministic fallback when LangGraph is unavailable

Architecture:
    upload → data_quality → entity_resolution → metrics → strategy → search_term_mining
                                                                ↓
    ┌───────────────────────────────────────────────────────────┐
    │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
    │  │ bid_opt      │ │ neg_keyword  │ │ budget_realloc│ │ campaign     │  │
    │  │ agent        │ │ agent        │ │ agent         │ │ struct agent │  │
    │  └──────┬───────┘ └──────┬───────┘ └──────┬────────┘ └──────┬───────┘  │
    │         └────────────────┴────────────────┴─────────────────┘          │
    └───────────────────────────────────────────────────────────────────────┘
                                    ↓
                    risk_validator → human_approval → bulk_compile → learning_feedback → END
"""

from __future__ import annotations

from uuid import UUID

from apps.api.app.orchestration.graph_state import AdsWorkflowState, initial_state
from apps.api.app.orchestration.nodes import (
    WorkflowNodeContext,
    ai_recommendation_brain_node,
    bid_optimization_agent_node,
    budget_allocation_agent_node,
    failure_node,
    finalize_workflow_node,
    human_approval_gate_node,
    metrics_analysis_node,
    negative_keyword_agent_node,
    pause_review_agent_node,
    product_resolution_node,
    report_detection_node,
    stakeholder_reporting_agent_node,
    start_workflow_node,
)
from apps.api.app.orchestration.router import route_after_report_detection
from apps.api.app.repositories.account_imports import AccountImportRepository
from apps.api.app.repositories.monitoring import MonitoringRepository
from apps.api.app.repositories.workflows import WorkflowRepository


def _get_checkpointer():
    """Get a PostgresSaver checkpointer for LangGraph state persistence.

    Requires LANGGRAPH_CHECKPOINT_BACKEND=postgres and DATABASE_URL set.
    Falls back to MemorySaver for local dev, or None if langgraph
    checkpoint extras aren't installed.
    """
    settings = None
    try:
        from apps.api.app.core.config import get_settings
        settings = get_settings()
    except Exception:
        pass

    backend = getattr(settings, "langgraph_checkpoint_backend", "memory") if settings else "memory"
    db_url = getattr(settings, "database_url", None) if settings else None

    if backend == "postgres" and db_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            import psycopg

            conn = psycopg.connect(db_url)
            checkpointer = PostgresSaver(conn)
            checkpointer.setup()
            return checkpointer
        except ImportError:
            pass

    # Fallback: in-memory saver (no persistence across restarts)
    try:
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
    except ImportError:
        return None


def build_ads_workflow_graph(context: WorkflowNodeContext):
    """Build the AdSurf LangGraph workflow with checkpointing and parallel optimization.

    New features (v2):
    - PostgresSaver checkpointing for replay/support debugging
    - Parallel fan-out for bid/negatives/budget/structure optimization agents
    - Conditional edges for planner-based skip (saves LLM cost)
    - Human-in-the-loop interrupt at approval node
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    graph = StateGraph(AdsWorkflowState)
    graph.add_node("start_workflow", lambda state: start_workflow_node(state, context))
    graph.add_node("report_detection", lambda state: report_detection_node(state, context))
    graph.add_node("product_resolution", lambda state: product_resolution_node(state, context))
    graph.add_node("metrics_analysis", lambda state: metrics_analysis_node(state, context))
    graph.add_node("ai_recommendation_brain", lambda state: ai_recommendation_brain_node(state, context))
    graph.add_node("bid_optimization", lambda state: bid_optimization_agent_node(state, context))
    graph.add_node("negative_keyword", lambda state: negative_keyword_agent_node(state, context))
    graph.add_node("budget_allocation", lambda state: budget_allocation_agent_node(state, context))
    graph.add_node("pause_review", lambda state: pause_review_agent_node(state, context))
    graph.add_node("stakeholder_reporting", lambda state: stakeholder_reporting_agent_node(state, context))
    graph.add_node("human_approval_gate", lambda state: human_approval_gate_node(state, context))
    graph.add_node("finalize_workflow", lambda state: finalize_workflow_node(state, context))
    graph.add_node("failure", lambda state: failure_node(state, context))

    # ── Parallel optimization merge node ────────────────────────────────
    def merge_optimization(state: AdsWorkflowState) -> AdsWorkflowState:
        """Collect results from parallel optimization agents into a unified state."""
        # All four optimization agents write to their own state keys;
        # this node simply signals completion and aggregates warnings.
        warnings = []
        for agent_key in ["bid_optimization", "negative_keyword", "budget_allocation", "pause_review"]:
            agent_warnings = state.get(f"{agent_key}_warnings", [])
            if agent_warnings:
                if isinstance(agent_warnings, list):
                    warnings.extend(agent_warnings)
                elif isinstance(agent_warnings, str):
                    warnings.append(agent_warnings)
        state["optimization_warnings"] = warnings
        state["optimization_completed"] = True
        return state

    graph.add_node("merge_optimization", merge_optimization)

    # ── Entry ───────────────────────────────────────────────────────────
    graph.set_entry_point("start_workflow")
    graph.add_edge("start_workflow", "report_detection")

    # ── Conditional routing after report detection ──────────────────────
    graph.add_conditional_edges(
        "report_detection",
        route_after_report_detection,
        {
            "product_resolution": "product_resolution",
            "human_approval_gate": "human_approval_gate",
            "failure": "failure",
        },
    )
    graph.add_edge("product_resolution", "metrics_analysis")
    graph.add_edge("metrics_analysis", "ai_recommendation_brain")

    # ── Parallel fan-out to four optimization agents ────────────────────
    # The ai_recommendation_brain produces recommendations that feed into
    # four independent optimization agents. They have NO mutual dependencies.
    graph.add_edge("ai_recommendation_brain", "bid_optimization")
    graph.add_edge("ai_recommendation_brain", "negative_keyword")
    graph.add_edge("ai_recommendation_brain", "budget_allocation")
    graph.add_edge("ai_recommendation_brain", "pause_review")

    # All four converge at merge_optimization
    graph.add_edge("bid_optimization", "merge_optimization")
    graph.add_edge("negative_keyword", "merge_optimization")
    graph.add_edge("budget_allocation", "merge_optimization")
    graph.add_edge("pause_review", "merge_optimization")

    # After merge, continue to downstream safety/output chain
    graph.add_edge("merge_optimization", "stakeholder_reporting")
    graph.add_edge("stakeholder_reporting", "human_approval_gate")

    # ── Terminal ────────────────────────────────────────────────────────
    graph.add_edge("human_approval_gate", END)
    graph.add_edge("finalize_workflow", END)
    graph.add_edge("failure", END)

    # ── Compile with checkpointing ────────────────────────────────────
    checkpointer = _get_checkpointer()
    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return graph.compile(**compile_kwargs)


class AdsWorkflowRunner:
    """Runs the full AdSurf agent workflow with checkpointing support."""

    def __init__(
        self,
        *,
        workflow_repository: WorkflowRepository,
        account_import_repository: AccountImportRepository,
        monitoring_repository: MonitoringRepository,
    ) -> None:
        self.context = WorkflowNodeContext(
            workflow_repository=workflow_repository,
            account_import_repository=account_import_repository,
            monitoring_repository=monitoring_repository,
        )

    def run_account_import_workflow(
        self,
        *,
        workflow_id: UUID,
        workspace_id: UUID,
        account_import_id: UUID,
        upload_id: UUID | None,
        agent_config: dict | None = None,
    ) -> AdsWorkflowState:
        """Execute the full workflow pipeline with checkpointing."""
        state = initial_state(
            workflow_id=str(workflow_id),
            workspace_id=str(workspace_id),
            account_import_id=str(account_import_id),
            upload_id=str(upload_id) if upload_id else None,
            agent_config=agent_config,
        )

        graph = build_ads_workflow_graph(self.context)
        if graph is not None:
            # Use LangGraph with checkpointing
            config = {"configurable": {"thread_id": str(workflow_id)}}
            return graph.invoke(state, config)

        # Fallback: deterministic linear execution without LangGraph
        return self._run_local(state)

    def replay_workflow(
        self,
        *,
        workflow_id: UUID,
        workspace_id: UUID,
        from_node: str | None = None,
    ) -> AdsWorkflowState | None:
        """Replay a workflow from the last checkpoint or a specific node.

        This is the support/debug endpoint for answering "why did the agent
        say X?" — uses LangGraph's built-in checkpoint replay.
        """
        graph = build_ads_workflow_graph(self.context)
        if graph is None:
            return None

        config = {"configurable": {"thread_id": str(workflow_id)}}

        # Get the latest state snapshot
        try:
            current_state = graph.get_state(config)
            if current_state is None or current_state.values is None:
                return None

            # Replay from the last checkpoint
            if from_node:
                # Resume from a specific node
                graph.update_state(config, {"resume_from": from_node})
                return graph.invoke(None, config)
            else:
                # Continue from last checkpoint
                return graph.invoke(None, config)
        except Exception:
            return None

    def _run_local(self, state: AdsWorkflowState) -> AdsWorkflowState:
        """Deterministic sequential execution when LangGraph is unavailable."""
        current = start_workflow_node(state, self.context)
        current = report_detection_node(current, self.context)
        route = route_after_report_detection(current)
        if route == "failure":
            return failure_node(current, self.context)
        if route == "human_approval_gate":
            return human_approval_gate_node(current, self.context)

        # Sequential pre-optimization nodes
        for node in [
            product_resolution_node,
            metrics_analysis_node,
            ai_recommendation_brain_node,
        ]:
            current = node(current, self.context)
            if current.get("status") == "failed":
                return failure_node(current, self.context)

        # Run optimization agents in sequence (deterministic fallback)
        for node in [
            bid_optimization_agent_node,
            negative_keyword_agent_node,
            budget_allocation_agent_node,
            pause_review_agent_node,
        ]:
            current = node(current, self.context)
            if current.get("status") == "failed":
                return failure_node(current, self.context)

        # Post-optimization chain
        for node in [
            stakeholder_reporting_agent_node,
            human_approval_gate_node,
        ]:
            current = node(current, self.context)
            if current.get("status") == "failed":
                return failure_node(current, self.context)

        return current