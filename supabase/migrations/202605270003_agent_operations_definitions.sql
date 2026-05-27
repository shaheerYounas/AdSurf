insert into agent_definitions (
    agent_id, display_name, description, task_type, enabled_by_default, allowed_actions,
    input_dependencies, output_type, can_be_disabled, can_be_rerun, can_be_stopped,
    requires_human_approval, can_mutate_live_amazon_ads
)
values
    ('report_upload_node', 'Report Upload', 'Receives Amazon Ads reports or bulk sheets and starts the account import workflow.', 'start', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '[]'::jsonb, 'uploaded_report', false, true, true, true, false),
    ('report_detection_agent', 'Report Detection Agent', 'Classifies the uploaded report type, required columns, confidence, and available entity levels.', 'validation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["report_upload_node"]'::jsonb, 'report_detection_summary', true, true, true, true, false),
    ('product_resolution_agent', 'Product Resolution Agent', 'Detects ASINs, SKUs, product names, and mapping suggestions before account-level analysis.', 'mapping', true, '["run","pause","stop","rerun","view_input","view_output","view_logs"]'::jsonb, '["report_detection_agent"]'::jsonb, 'product_mapping_suggestions', true, true, true, true, false),
    ('budget_allocation_agent', 'Budget Allocation Agent', 'Reviews campaign and product budget pressure and suggests approval-gated budget review actions.', 'explanation', true, '["run","pause","stop","rerun","view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["ai_recommendation_brain_agent"]'::jsonb, 'budget_recommendation_explanations', true, true, true, true, false),
    ('human_approval_agent', 'Human Approval Agent', 'Routes recommendations to the approval queue and prevents automatic approval or live ad mutation.', 'approval', true, '["view_input","view_output","view_logs","view_recommendations"]'::jsonb, '["stakeholder_reporting_agent"]'::jsonb, 'approval_queue', false, false, false, true, false)
on conflict (agent_id) do update set
    display_name = excluded.display_name,
    description = excluded.description,
    task_type = excluded.task_type,
    enabled_by_default = excluded.enabled_by_default,
    allowed_actions = excluded.allowed_actions,
    input_dependencies = excluded.input_dependencies,
    output_type = excluded.output_type,
    can_be_disabled = excluded.can_be_disabled,
    can_be_rerun = excluded.can_be_rerun,
    can_be_stopped = excluded.can_be_stopped,
    requires_human_approval = excluded.requires_human_approval,
    can_mutate_live_amazon_ads = excluded.can_mutate_live_amazon_ads,
    updated_at = now();
