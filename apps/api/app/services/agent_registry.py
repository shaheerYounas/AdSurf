from apps.api.app.schemas.agent_control import AgentDefinition


AGENT_WORKFLOW_ORDER = [
    "performance_import_agent",
    "metrics_analysis_agent",
    "ai_recommendation_brain_agent",
    "bid_optimization_agent",
    "negative_keyword_agent",
    "pause_review_agent",
    "stakeholder_reporting_agent",
]


AGENT_DEFINITIONS = [
    AgentDefinition(
        agent_id="performance_import_agent",
        display_name="Performance Import Agent",
        description="Validates report quality, missing columns, row count, and data-quality warnings.",
        task_type="validation",
        input_dependencies=[],
        output_type="report_quality_summary",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
    ),
    AgentDefinition(
        agent_id="metrics_analysis_agent",
        display_name="Metrics Analysis Agent",
        description="Analyzes uploaded Amazon Ads performance metrics and finds winners, wasters, and risks.",
        task_type="analysis",
        input_dependencies=["performance_import_agent"],
        output_type="performance_summary",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
    ),
    AgentDefinition(
        agent_id="ai_recommendation_brain_agent",
        display_name="AI Recommendation Brain",
        description="Uses DeepSeek or configured fallback mode to generate recommendation decisions from normalized report evidence.",
        task_type="decision",
        input_dependencies=["metrics_analysis_agent"],
        output_type="recommendation_json",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="bid_optimization_agent",
        display_name="Bid Optimization Agent",
        description="Reviews bid-related recommendations and explains increase, decrease, watch-lock, and bid risk logic.",
        task_type="explanation",
        input_dependencies=["ai_recommendation_brain_agent"],
        output_type="bid_recommendation_explanations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="negative_keyword_agent",
        display_name="Negative Keyword Agent",
        description="Reviews wasted search terms and explains negative exact or phrase evidence.",
        task_type="explanation",
        input_dependencies=["ai_recommendation_brain_agent"],
        output_type="negative_keyword_explanations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="pause_review_agent",
        display_name="Pause Review Agent",
        description="Reviews campaigns, ad groups, targets, or search terms that may need pause review.",
        task_type="explanation",
        input_dependencies=["ai_recommendation_brain_agent"],
        output_type="pause_review_explanations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="stakeholder_reporting_agent",
        display_name="Stakeholder Reporting Agent",
        description="Creates dashboard summaries, executive summary, next-best actions, and approver notes.",
        task_type="reporting",
        input_dependencies=["bid_optimization_agent", "negative_keyword_agent", "pause_review_agent"],
        output_type="dashboard_summary",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
    ),
]


AGENT_DEFINITION_BY_ID = {agent.agent_id: agent for agent in AGENT_DEFINITIONS}
AGENT_NAME_TO_ID = {
    "performance_import_agent": "performance_import_agent",
    "metrics_analysis_agent": "metrics_analysis_agent",
    "monitoring_recommendation_brain": "ai_recommendation_brain_agent",
    "ai_recommendation_brain_agent": "ai_recommendation_brain_agent",
    "bid_optimization_agent": "bid_optimization_agent",
    "negative_keyword_agent": "negative_keyword_agent",
    "pause_review_agent": "pause_review_agent",
    "stakeholder_reporting_agent": "stakeholder_reporting_agent",
}


def list_agent_definitions() -> list[AgentDefinition]:
    return AGENT_DEFINITIONS


def agent_id_for_run_name(agent_name: str) -> str:
    return AGENT_NAME_TO_ID.get(agent_name, agent_name)
