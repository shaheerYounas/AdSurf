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


def build_ads_workflow_graph(context: WorkflowNodeContext):
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

    graph.set_entry_point("start_workflow")
    graph.add_edge("start_workflow", "report_detection")
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
    graph.add_edge("ai_recommendation_brain", "bid_optimization")
    graph.add_edge("bid_optimization", "negative_keyword")
    graph.add_edge("negative_keyword", "budget_allocation")
    graph.add_edge("budget_allocation", "pause_review")
    graph.add_edge("pause_review", "stakeholder_reporting")
    graph.add_edge("stakeholder_reporting", "human_approval_gate")
    graph.add_edge("human_approval_gate", END)
    graph.add_edge("finalize_workflow", END)
    graph.add_edge("failure", END)
    return graph.compile()


class AdsWorkflowRunner:
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
        state = initial_state(
            workflow_id=str(workflow_id),
            workspace_id=str(workspace_id),
            account_import_id=str(account_import_id),
            upload_id=str(upload_id) if upload_id else None,
            agent_config=agent_config,
        )
        graph = build_ads_workflow_graph(self.context)
        if graph is not None:
            return graph.invoke(state)
        return self._run_local(state)

    def _run_local(self, state: AdsWorkflowState) -> AdsWorkflowState:
        current = start_workflow_node(state, self.context)
        current = report_detection_node(current, self.context)
        route = route_after_report_detection(current)
        if route == "failure":
            return failure_node(current, self.context)
        if route == "human_approval_gate":
            return human_approval_gate_node(current, self.context)
        for node in [
            product_resolution_node,
            metrics_analysis_node,
            ai_recommendation_brain_node,
            bid_optimization_agent_node,
            negative_keyword_agent_node,
            budget_allocation_agent_node,
            pause_review_agent_node,
            stakeholder_reporting_agent_node,
            human_approval_gate_node,
        ]:
            current = node(current, self.context)
            if current.get("status") == "failed":
                return failure_node(current, self.context)
        return current
