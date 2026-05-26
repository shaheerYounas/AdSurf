create index if not exists product_profiles_workspace_created_desc_idx
    on product_profiles(workspace_id, created_at desc);

create index if not exists uploads_workspace_created_desc_idx
    on uploads(workspace_id, created_at desc);

create index if not exists uploads_workspace_status_created_desc_idx
    on uploads(workspace_id, status, created_at desc);

create index if not exists recommendations_workspace_product_status_priority_created_idx
    on recommendations(workspace_id, product_id, status, priority, created_at desc);

create index if not exists recommendations_workspace_priority_created_idx
    on recommendations(workspace_id, priority, created_at desc);

create index if not exists ai_runs_workspace_product_agent_created_idx
    on ai_runs(workspace_id, product_id, agent_name, created_at desc);
