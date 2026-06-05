from apps.api.app.schemas.agent_control import AgentDefinition


AGENT_WORKFLOW_ORDER = [
    "import_data_quality_agent",
    "entity_resolution_agent",
    "metrics_normalization_agent",
    "account_strategy_agent",
    "search_term_mining_agent",
    "bid_optimization_agent",
    "negative_keyword_agent",
    "budget_reallocation_agent",
    "campaign_structure_agent",
    "risk_policy_validator_agent",
    "ai_recommendation_brain_agent",
    "bulk_change_compiler_agent",
    "learning_feedback_agent",
    "stakeholder_reporting_agent",
    "human_approval_agent",
]


AGENT_DEFINITIONS = [
    # ===== DATA PIPELINE =====
    AgentDefinition(
        agent_id="import_data_quality_agent",
        display_name="Import & Data Quality Agent",
        description="Checks uploaded reports for missing columns, wrong date ranges, mixed marketplaces, duplicate rows, currency mismatches, low sample sizes, old data, and suspicious rows. Outputs a data quality score and usable flag.",
        task_type="validation",
        category="data_pipeline",
        input_dependencies=["report_upload_node"],
        output_type="data_quality_report",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
        can_be_disabled=False,
    ),
    AgentDefinition(
        agent_id="entity_resolution_agent",
        display_name="Entity Resolution Agent",
        description="Maps campaigns, ad groups, SKUs, ASINs, search terms, keywords, targeting expressions, match types, portfolios, and marketplaces. Ensures correct entity mapping before optimization decisions.",
        task_type="mapping",
        category="data_pipeline",
        input_dependencies=["import_data_quality_agent"],
        output_type="entity_mapping",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
    ),
    AgentDefinition(
        agent_id="metrics_normalization_agent",
        display_name="Metrics Normalization Agent",
        description="Calculates all performance metrics deterministically: spend, sales, orders, clicks, impressions, CPC, CTR, CVR, ACOS, ROAS, CPA, revenue per click, profit estimate, and break-even ACOS. AI does not calculate metrics.",
        task_type="analysis",
        category="analysis",
        input_dependencies=["entity_resolution_agent"],
        output_type="normalized_metrics",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
        can_be_disabled=True,
        can_use_ai=False,
    ),

    # ===== ANALYSIS =====
    AgentDefinition(
        agent_id="account_strategy_agent",
        display_name="Account Strategy Agent",
        description="Determines the seller's optimization goal: profit, growth, launch, rank defense, inventory clearance, brand defense, competitor conquesting, or wasted spend cleanup. Configures thresholds, risk tolerance, and approval policies per strategy mode.",
        task_type="strategy",
        category="analysis",
        input_dependencies=["metrics_normalization_agent"],
        output_type="strategy_configuration",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_configuration"],
        can_be_disabled=False,
    ),
    AgentDefinition(
        agent_id="search_term_mining_agent",
        display_name="Search Term Mining Agent",
        description="Classifies search terms into actionable categories: harvest to exact/phrase, keep broad discovery, add negative exact/phrase, watch, ignore low data, brand defense, competitor term, research intent, irrelevant intent. Upgrades keyword scoring to full search term intelligence.",
        task_type="analysis",
        category="analysis",
        input_dependencies=["metrics_normalization_agent", "account_strategy_agent"],
        output_type="search_term_classifications",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),

    # ===== OPTIMIZATION =====
    AgentDefinition(
        agent_id="bid_optimization_agent",
        display_name="Bid Optimization Agent",
        description="Generates exact bid change recommendations with current bid, recommended bid, change percent, risk level, and evidence. Outputs increase_bid, decrease_bid, and set_bid actions with full evidence scoring.",
        task_type="decision",
        category="optimization",
        input_dependencies=["search_term_mining_agent", "account_strategy_agent"],
        output_type="bid_recommendations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="negative_keyword_agent",
        display_name="Negative Keyword Agent",
        description="Reviews wasted search terms and generates negative exact/phrase recommendations with evidence thresholds, converting-term protection, and strategy-aware logic.",
        task_type="decision",
        category="optimization",
        input_dependencies=["search_term_mining_agent", "account_strategy_agent"],
        output_type="negative_keyword_recommendations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="budget_reallocation_agent",
        display_name="Budget Reallocation Agent",
        description="Analyzes campaigns across portfolio: out-of-budget-but-profitable, spending-but-unprofitable, no impressions, strong ROAS with limited budget, discovery campaigns that should stay capped. Recommends budget shifts between campaigns.",
        task_type="decision",
        category="optimization",
        input_dependencies=["metrics_normalization_agent", "account_strategy_agent"],
        output_type="budget_recommendations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),
    AgentDefinition(
        agent_id="campaign_structure_agent",
        display_name="Campaign Structure Agent",
        description="Recommends structural changes: move converting search terms to exact, create isolated exact campaigns for hero terms, separate branded/non-branded, separate competitor targeting, separate product from keyword targeting, separate launch from profit campaigns, separate high/low margin products.",
        task_type="decision",
        category="optimization",
        input_dependencies=["search_term_mining_agent", "bid_optimization_agent", "account_strategy_agent"],
        output_type="campaign_structure_recommendations",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
    ),

    # ===== SAFETY =====
    AgentDefinition(
        agent_id="risk_policy_validator_agent",
        display_name="Risk & Policy Validator Agent",
        description="Rejects unsafe actions: bid increase above max, budget increase above limit, negative keyword on converting term, pause with too little data, duplicate bulk actions, conflicting actions on same target, recommendation without evidence, low sample size recommendations, strategy violations. Deterministic validation with AI only explaining risk.",
        task_type="validation",
        category="safety",
        input_dependencies=["bid_optimization_agent", "negative_keyword_agent", "budget_reallocation_agent", "campaign_structure_agent"],
        output_type="validation_report",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_validation"],
        can_be_disabled=False,
        can_use_ai=False,
    ),
    AgentDefinition(
        agent_id="human_approval_agent",
        display_name="Human Approval Agent",
        description="Routes validated recommendations to the approval queue. Prevents automatic approval or live ad mutation. Every customer-impacting action requires explicit human approval record with audit trail.",
        task_type="approval",
        category="safety",
        input_dependencies=["risk_policy_validator_agent"],
        output_type="approval_queue",
        allowed_actions=["view_input", "view_output", "view_logs", "view_recommendations", "view_approval_queue"],
        can_be_disabled=False,
        can_be_rerun=False,
        can_be_stopped=False,
    ),

    # ===== OUTPUT =====
    AgentDefinition(
        agent_id="bulk_change_compiler_agent",
        display_name="Bulk Change Compiler Agent",
        description="Generates approved changes table, rejected changes table, Amazon bulk upload file, human-readable change summary, audit log, before/after comparison, and rollback reference from approved recommendations.",
        task_type="export",
        category="output",
        input_dependencies=["human_approval_agent"],
        output_type="bulk_export",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "download_export"],
        can_be_disabled=False,
    ),
    AgentDefinition(
        agent_id="learning_feedback_agent",
        display_name="Learning & Feedback Agent",
        description="Compares previous recommendations with current report data. Tracks whether implemented changes improved metrics. Builds optimization memory over time. Adjusts rule confidence based on outcome history. Turns the app from a static analyzer into a real optimization system.",
        task_type="analysis",
        category="output",
        input_dependencies=["bulk_change_compiler_agent"],
        output_type="learning_report",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
    ),
    AgentDefinition(
        agent_id="stakeholder_reporting_agent",
        display_name="Stakeholder Reporting Agent",
        description="Creates dashboard summaries, executive summaries, next-best actions, and approver notes for owners, analysts, and approvers. Includes optimization impact metrics: total spend analyzed, wasted spend detected, estimated savings, recommendation counts by type.",
        task_type="reporting",
        category="output",
        input_dependencies=["learning_feedback_agent"],
        output_type="dashboard_summary",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
    ),

    # Legacy agents kept for backward compatibility
    AgentDefinition(
        agent_id="report_upload_node",
        display_name="Report Upload",
        description="Receives Amazon Ads reports or bulk sheets and starts the account import workflow.",
        task_type="start",
        category="data_pipeline",
        input_dependencies=[],
        output_type="uploaded_report",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
        can_be_disabled=False,
    ),
    AgentDefinition(
        agent_id="performance_import_agent",
        display_name="Performance Import Agent (Legacy)",
        description="[Legacy] Imports and validates Amazon Ads performance reports. Mapped to Import & Data Quality Agent for current workflows.",
        task_type="validation",
        category="legacy",
        input_dependencies=["report_upload_node"],
        output_type="data_quality_report",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
        can_be_disabled=True,
    ),
    AgentDefinition(
        agent_id="metrics_analysis_agent",
        display_name="Metrics Analysis Agent (Legacy)",
        description="[Legacy] Calculates performance metrics. Mapped to Metrics Normalization Agent for current workflows.",
        task_type="analysis",
        category="legacy",
        input_dependencies=["performance_import_agent"],
        output_type="normalized_metrics",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"],
        can_be_disabled=True,
        can_use_ai=False,
    ),
    AgentDefinition(
        agent_id="ai_recommendation_brain_agent",
        display_name="AI Recommendation Brain (Legacy)",
        description="[Legacy] Uses AI to generate recommendation decisions. Now split into account_strategy_agent, search_term_mining_agent, bid_optimization_agent, and campaign_structure_agent. Kept for backward compatibility with existing workflows.",
        task_type="decision",
        category="legacy",
        input_dependencies=["metrics_analysis_agent"],
        output_type="recommendation_json",
        allowed_actions=["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs", "view_recommendations"],
        can_be_disabled=True,
    ),
]


AGENT_DEFINITION_BY_ID = {agent.agent_id: agent for agent in AGENT_DEFINITIONS}

AGENT_NAME_TO_ID = {
    "report_upload_node": "report_upload_node",
    "import_data_quality_agent": "import_data_quality_agent",
    "entity_resolution_agent": "entity_resolution_agent",
    "metrics_normalization_agent": "metrics_normalization_agent",
    "account_strategy_agent": "account_strategy_agent",
    "search_term_mining_agent": "search_term_mining_agent",
    "bid_optimization_agent": "bid_optimization_agent",
    "negative_keyword_agent": "negative_keyword_agent",
    "budget_reallocation_agent": "budget_reallocation_agent",
    "campaign_structure_agent": "campaign_structure_agent",
    "risk_policy_validator_agent": "risk_policy_validator_agent",
    "human_approval_agent": "human_approval_agent",
    "bulk_change_compiler_agent": "bulk_change_compiler_agent",
    "learning_feedback_agent": "learning_feedback_agent",
    "stakeholder_reporting_agent": "stakeholder_reporting_agent",
    # Legacy mappings
    "ai_recommendation_brain_agent": "ai_recommendation_brain_agent",
    "performance_import_agent": "import_data_quality_agent",
    "metrics_analysis_agent": "metrics_normalization_agent",
    "monitoring_recommendation_brain": "ai_recommendation_brain_agent",
    "product_resolution_agent": "entity_resolution_agent",
    "report_detection_agent": "import_data_quality_agent",
    "budget_allocation_agent": "budget_reallocation_agent",
    "pause_review_agent": "bid_optimization_agent",
}


# Agent group definitions for UI grouping
AGENT_GROUPS = {
    "data_pipeline": {
        "label": "Data Pipeline",
        "description": "Import, validate, and resolve entity mappings before analysis",
        "agents": ["import_data_quality_agent", "entity_resolution_agent", "report_upload_node"],
        "icon": "upload",
    },
    "analysis": {
        "label": "Analysis",
        "description": "Calculate metrics, detect patterns, and set strategy",
        "agents": ["metrics_normalization_agent", "account_strategy_agent", "search_term_mining_agent"],
        "icon": "chart",
    },
    "optimization": {
        "label": "Optimization",
        "description": "Generate bid, negative keyword, budget, and structure recommendations",
        "agents": ["bid_optimization_agent", "negative_keyword_agent", "budget_reallocation_agent", "campaign_structure_agent"],
        "icon": "target",
    },
    "safety": {
        "label": "Safety",
        "description": "Validate, approve, and audit every recommendation before export",
        "agents": ["risk_policy_validator_agent", "human_approval_agent"],
        "icon": "shield",
    },
    "output": {
        "label": "Output",
        "description": "Compile bulk exports, learn from outcomes, and report to stakeholders",
        "agents": ["bulk_change_compiler_agent", "learning_feedback_agent", "stakeholder_reporting_agent"],
        "icon": "download",
    },
}


def list_agent_definitions() -> list[AgentDefinition]:
    return AGENT_DEFINITIONS


def list_active_agent_definitions() -> list[AgentDefinition]:
    return [a for a in AGENT_DEFINITIONS if a.category != "legacy"]


def agent_id_for_run_name(agent_name: str) -> str:
    return AGENT_NAME_TO_ID.get(agent_name, agent_name)


def agent_definitions_by_group() -> dict[str, list[AgentDefinition]]:
    """Return agent definitions organized by UI group."""
    result = {}
    for group_key, group_info in AGENT_GROUPS.items():
        result[group_key] = [
            AGENT_DEFINITION_BY_ID[agent_id]
            for agent_id in group_info["agents"]
            if agent_id in AGENT_DEFINITION_BY_ID
        ]
    return result
