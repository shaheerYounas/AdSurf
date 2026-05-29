-- Custom Agent Builder Foundation
-- Enables users to create, configure, and run custom AI agents with tools, knowledge bases, sub-agents, memory, and approval gates.

-- ============================================================================
-- Custom Agents (user-created agent configurations)
-- ============================================================================
create table if not exists custom_agents (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    name text not null,
    description text,
    role_instructions text,               -- system prompt / agent instructions
    model_provider text not null default 'deepseek',  -- 'openai', 'anthropic', 'deepseek', 'google', 'local'
    model_name text not null default 'deepseek-chat',
    temperature numeric(3,2) default 0.7 check (temperature >= 0 and temperature <= 2),
    max_tokens integer default 4096,
    memory_enabled boolean not null default false,
    memory_ttl_days integer default 30,
    output_format text default 'text',     -- 'text', 'json', 'markdown', 'table', 'code', 'email'
    output_schema jsonb,                   -- structured output JSON schema
    workflow_type text default 'sequential', -- 'sequential', 'parallel', 'supervisor', 'custom'
    workflow_graph jsonb,                  -- visual workflow graph definition
    status text not null default 'draft' check (status in ('draft', 'active', 'paused', 'archived')),
    metadata_json jsonb not null default '{}'::jsonb,
    created_by uuid,
    updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================================
-- Agent Tools (tools available to each custom agent)
-- ============================================================================
create table if not exists agent_tools (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id uuid not null references custom_agents(id) on delete cascade,
    tool_name text not null,               -- 'web_search', 'github', 'browser', 'gmail', 'database', 'crm', 'custom_api'
    tool_config jsonb not null default '{}'::jsonb,
    enabled boolean not null default true,
    permission_level text not null default 'read' check (permission_level in ('read', 'write', 'execute', 'admin')),
    requires_approval boolean not null default false,
    rate_limit_per_day integer,
    allowed_domains jsonb,                 -- domain allowlist for web tools
    allowed_actions jsonb,                 -- specific allowed actions within this tool
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(agent_id, tool_name)
);

-- ============================================================================
-- Knowledge Bases (uploaded documents connected to agents)
-- ============================================================================
create table if not exists knowledge_bases (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    name text not null,
    description text,
    source_type text not null default 'upload', -- 'upload', 'url', 'api', 'manual'
    file_count integer not null default 0,
    chunk_count integer not null default 0,
    embedding_model text default 'text-embedding-3-small',
    embedding_provider text default 'openai',
    status text not null default 'pending' check (status in ('pending', 'processing', 'ready', 'error')),
    created_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================================
-- Knowledge Base Files (individual files within a knowledge base)
-- ============================================================================
create table if not exists knowledge_base_files (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    knowledge_base_id uuid not null references knowledge_bases(id) on delete cascade,
    file_name text not null,
    file_path text not null,
    file_type text not null,
    file_size_bytes bigint,
    chunk_count integer not null default 0,
    status text not null default 'pending' check (status in ('pending', 'processing', 'ready', 'error')),
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================================
-- Knowledge Base Chunks (embedded text chunks for RAG)
-- ============================================================================
create table if not exists knowledge_base_chunks (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    knowledge_base_id uuid not null references knowledge_bases(id) on delete cascade,
    file_id uuid references knowledge_base_files(id) on delete set null,
    chunk_index integer not null,
    content text not null,
    token_count integer,
    embedding vector(1536),               -- pgvector extension required
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- Agent-Knowledge Base Links (many-to-many)
-- ============================================================================
create table if not exists agent_knowledge_bases (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id uuid not null references custom_agents(id) on delete cascade,
    knowledge_base_id uuid not null references knowledge_bases(id) on delete cascade,
    retrieval_priority integer default 1,
    max_chunks_per_query integer default 5,
    similarity_threshold numeric(3,2) default 0.75,
    created_at timestamptz not null default now(),
    unique(agent_id, knowledge_base_id)
);

-- ============================================================================
-- Sub-Agents (specialist agents that compose a multi-agent system)
-- ============================================================================
create table if not exists sub_agents (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    parent_agent_id uuid not null references custom_agents(id) on delete cascade,
    name text not null,
    role text not null,                    -- 'researcher', 'writer', 'reviewer', 'coder', 'analyst', 'planner'
    instructions text not null,
    model_provider text,
    model_name text,
    tools_json jsonb not null default '[]'::jsonb,
    execution_order integer not null default 1,
    enabled boolean not null default true,
    requires_approval boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================================
-- Conversation Threads (persistent conversations with agents)
-- ============================================================================
create table if not exists agent_threads (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id uuid not null references custom_agents(id) on delete cascade,
    title text,
    status text not null default 'active' check (status in ('active', 'paused', 'completed', 'archived')),
    metadata_json jsonb not null default '{}'::jsonb,
    created_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================================
-- Messages (individual messages within a thread)
-- ============================================================================
create table if not exists agent_messages (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    thread_id uuid not null references agent_threads(id) on delete cascade,
    agent_id uuid references custom_agents(id) on delete set null,
    role text not null check (role in ('user', 'assistant', 'system', 'tool', 'sub_agent')),
    content text,
    tool_calls_json jsonb,
    tool_call_id text,
    sub_agent_name text,
    token_count integer,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- Agent Memories (long-term memory entries)
-- ============================================================================
create table if not exists agent_memories (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id uuid not null references custom_agents(id) on delete cascade,
    thread_id uuid references agent_threads(id) on delete set null,
    memory_type text not null default 'preference' check (memory_type in ('preference', 'fact', 'decision', 'context', 'user_info', 'project')),
    content text not null,
    embedding vector(1536),
    importance numeric(3,2) default 0.5,
    access_count integer not null default 0,
    last_accessed_at timestamptz,
    expires_at timestamptz,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================================
-- Agent Runs (execution records for custom agents)
-- ============================================================================
create table if not exists custom_agent_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id uuid not null references custom_agents(id) on delete cascade,
    thread_id uuid references agent_threads(id) on delete set null,
    status text not null default 'queued' check (status in ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled', 'waiting_approval')),
    model_provider text,
    model_name text,
    input_json jsonb not null default '{}'::jsonb,
    output_json jsonb not null default '{}'::jsonb,
    error_json jsonb not null default '{}'::jsonb,
    tokens_input integer default 0,
    tokens_output integer default 0,
    cost_usd numeric(12,6) default 0,
    latency_ms integer,
    sub_agent_runs_json jsonb not null default '[]'::jsonb,
    tool_call_count integer default 0,
    knowledge_chunks_retrieved integer default 0,
    metadata_json jsonb not null default '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- Agent Run Steps (fine-grained step tracking within a run)
-- ============================================================================
create table if not exists custom_agent_run_steps (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    run_id uuid not null references custom_agent_runs(id) on delete cascade,
    agent_name text,                       -- which agent/sub-agent performed this step
    step_type text not null check (step_type in ('planner', 'research', 'tool_call', 'knowledge_retrieval', 'llm_call', 'sub_agent', 'reviewer', 'output_format', 'approval_check')),
    step_order integer not null,
    input_json jsonb not null default '{}'::jsonb,
    output_json jsonb not null default '{}'::jsonb,
    status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed', 'skipped')),
    error_message text,
    latency_ms integer,
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

-- ============================================================================
-- Agent Secrets (encrypted API keys and credentials for tools)
-- ============================================================================
create table if not exists agent_secrets (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete restrict,
    agent_id uuid references custom_agents(id) on delete cascade,
    secret_name text not null,             -- 'openai_api_key', 'github_token', 'gmail_credentials', etc.
    secret_value_encrypted text,           -- encrypted at rest
    secret_provider text,                  -- vault backend reference
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(agent_id, secret_name)
);

-- ============================================================================
-- Agent Templates (pre-built agent configurations users can clone)
-- ============================================================================
create table if not exists agent_templates (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    description text not null,
    category text not null,                -- 'marketing', 'sales', 'development', 'support', 'research', 'general'
    config_json jsonb not null,            -- full agent config to clone
    is_public boolean not null default true,
    usage_count integer not null default 0,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- Indexes
-- ============================================================================
create index if not exists custom_agents_workspace_idx on custom_agents(workspace_id, status, created_at desc);
create index if not exists custom_agents_name_idx on custom_agents(workspace_id, name);
create index if not exists agent_tools_agent_idx on agent_tools(agent_id);
create index if not exists knowledge_bases_workspace_idx on knowledge_bases(workspace_id, created_at desc);
create index if not exists knowledge_base_files_kb_idx on knowledge_base_files(knowledge_base_id, status);
create index if not exists knowledge_base_chunks_kb_idx on knowledge_base_chunks(knowledge_base_id, chunk_index);
-- pgvector index for similarity search
-- create index if not exists knowledge_base_chunks_embedding_idx on knowledge_base_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists agent_knowledge_bases_agent_idx on agent_knowledge_bases(agent_id, knowledge_base_id);
create index if not exists sub_agents_parent_idx on sub_agents(parent_agent_id, execution_order);
create index if not exists agent_threads_agent_idx on agent_threads(agent_id, updated_at desc);
create index if not exists agent_threads_workspace_idx on agent_threads(workspace_id, created_at desc);
create index if not exists agent_messages_thread_idx on agent_messages(thread_id, created_at);
create index if not exists agent_memories_agent_idx on agent_memories(agent_id, memory_type);
-- create index if not exists agent_memories_embedding_idx on agent_memories using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists custom_agent_runs_agent_idx on custom_agent_runs(agent_id, created_at desc);
create index if not exists custom_agent_runs_thread_idx on custom_agent_runs(thread_id, created_at desc);
create index if not exists custom_agent_run_steps_run_idx on custom_agent_run_steps(run_id, step_order);
create index if not exists agent_secrets_agent_idx on agent_secrets(agent_id, secret_name);

-- ============================================================================
-- Row Level Security
-- ============================================================================
alter table custom_agents enable row level security;
alter table agent_tools enable row level security;
alter table knowledge_bases enable row level security;
alter table knowledge_base_files enable row level security;
alter table knowledge_base_chunks enable row level security;
alter table agent_knowledge_bases enable row level security;
alter table sub_agents enable row level security;
alter table agent_threads enable row level security;
alter table agent_messages enable row level security;
alter table agent_memories enable row level security;
alter table custom_agent_runs enable row level security;
alter table custom_agent_run_steps enable row level security;
alter table agent_secrets enable row level security;
alter table agent_templates enable row level security;

-- Workspace-scoped select policies
create policy custom_agents_select_workspace on custom_agents for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_tools_select_workspace on agent_tools for select using (public.current_user_is_workspace_member(workspace_id));
create policy knowledge_bases_select_workspace on knowledge_bases for select using (public.current_user_is_workspace_member(workspace_id));
create policy knowledge_base_files_select_workspace on knowledge_base_files for select using (public.current_user_is_workspace_member(workspace_id));
create policy knowledge_base_chunks_select_workspace on knowledge_base_chunks for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_knowledge_bases_select_workspace on agent_knowledge_bases for select using (public.current_user_is_workspace_member(workspace_id));
create policy sub_agents_select_workspace on sub_agents for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_threads_select_workspace on agent_threads for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_messages_select_workspace on agent_messages for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_memories_select_workspace on agent_memories for select using (public.current_user_is_workspace_member(workspace_id));
create policy custom_agent_runs_select_workspace on custom_agent_runs for select using (public.current_user_is_workspace_member(workspace_id));
create policy custom_agent_run_steps_select_workspace on custom_agent_run_steps for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_secrets_select_workspace on agent_secrets for select using (public.current_user_is_workspace_member(workspace_id));
create policy agent_templates_select_all on agent_templates for select using (true);

-- Write policies (owner, admin, analyst for most; owner/admin only for secrets)
create policy custom_agents_write_workspace on custom_agents for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_tools_write_workspace on agent_tools for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy knowledge_bases_write_workspace on knowledge_bases for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy knowledge_base_files_write_workspace on knowledge_base_files for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy knowledge_base_chunks_write_workspace on knowledge_base_chunks for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_knowledge_bases_write_workspace on agent_knowledge_bases for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy sub_agents_write_workspace on sub_agents for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_threads_write_workspace on agent_threads for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_messages_write_workspace on agent_messages for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_memories_write_workspace on agent_memories for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy custom_agent_runs_write_workspace on custom_agent_runs for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy custom_agent_run_steps_write_workspace on custom_agent_run_steps for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin', 'analyst']));
create policy agent_secrets_write_admins on agent_secrets for all
    using (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin']))
    with check (public.current_user_has_workspace_role(workspace_id, array['owner', 'admin']));
create policy agent_templates_insert_admins on agent_templates for insert
    with check (exists (select 1 from workspaces where workspaces.id = (select workspace_id from custom_agents where custom_agents.id = agent_templates.config_json->>'created_from_agent_id' limit 1)));

-- ============================================================================
-- Seed agent templates
-- ============================================================================
insert into agent_templates (name, description, category, config_json) values
    ('Marketing Research Agent', 'Researches competitors, market trends, and writes content briefs. Has web search, knowledge base, and sub-agents for research, writing, and review.', 'marketing', '{"name":"Marketing Research Agent","role_instructions":"You are an expert marketing researcher. Research competitors thoroughly, analyze market trends, and produce well-structured content briefs. Always cite sources.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.7,"memory_enabled":true,"tools":["web_search"],"sub_agents":[{"name":"Research Agent","role":"Analyze competitor websites and gather market data","instructions":"Search for competitor information and compile comprehensive research reports."},{"name":"Writer Agent","role":"Create polished marketing content","instructions":"Write clear, engaging marketing content based on research findings."},{"name":"Reviewer Agent","role":"Check for accuracy and quality","instructions":"Verify facts, check grammar, and ensure content meets quality standards."}],"permissions":{"requires_approval_before_email":true,"can_read_web":true,"can_write_web":false}}'),

    ('Sales Outreach Agent', 'Qualifies leads, drafts personalized emails, and manages follow-up cadences. Connects to CRM and email with human approval.', 'sales', '{"name":"Sales Outreach Agent","role_instructions":"You are a professional sales development representative. Qualify leads carefully, write personalized outreach emails, and suggest optimal follow-up timing. Never send emails without human approval.","model_provider":"openai","model_name":"gpt-4o","temperature":0.5,"memory_enabled":true,"tools":["crm_lookup","email_draft"],"sub_agents":[{"name":"Lead Qualifier","role":"Evaluate lead fit and priority","instructions":"Score leads based on ICP criteria and prioritize outreach."},{"name":"Email Drafter","role":"Write personalized outreach emails","instructions":"Craft compelling, personalized emails that reference specific trigger events."}],"permissions":{"requires_approval_before_email":true,"can_read_crm":true,"can_send_email":false}}'),

    ('Code Review Agent', 'Reviews pull requests, suggests improvements, checks security vulnerabilities, and explains code changes. Connects to GitHub.', 'development', '{"name":"Code Review Agent","role_instructions":"You are a senior software engineer performing code reviews. Check for bugs, security issues, performance problems, and adherence to best practices. Be constructive and educational.","model_provider":"openai","model_name":"gpt-4o","temperature":0.3,"memory_enabled":false,"tools":["github_repo_reader"],"sub_agents":[{"name":"Security Reviewer","role":"Check for security vulnerabilities","instructions":"Scan code for OWASP top 10 vulnerabilities and insecure patterns."},{"name":"Performance Reviewer","role":"Identify performance issues","instructions":"Check for N+1 queries, memory leaks, and inefficient algorithms."},{"name":"Style Reviewer","role":"Check code style and best practices","instructions":"Verify code follows team conventions and language idioms."}],"permissions":{"can_read_github":true,"can_write_github":false,"can_create_pr_comment":false}}'),

    ('Customer Support Agent', 'Answers customer questions from knowledge base, drafts responses, and escalates complex issues. Connects to documentation and ticketing systems.', 'support', '{"name":"Customer Support Agent","role_instructions":"You are a helpful customer support specialist. Answer questions accurately using the knowledge base. If unsure, acknowledge limitations and suggest escalation. Always be empathetic and professional.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.4,"memory_enabled":true,"tools":["knowledge_base_search","ticket_lookup"],"sub_agents":[],"permissions":{"can_read_knowledge_base":true,"can_read_tickets":true,"can_update_tickets":false,"requires_approval_before_customer_reply":true}}'),

    ('General Research Assistant', 'Versatile research agent with web search, file analysis, and summarization capabilities. Good starting point for customization.', 'general', '{"name":"General Research Assistant","role_instructions":"You are a helpful research assistant. Find accurate information, summarize findings clearly, and cite your sources. Ask clarifying questions when needed.","model_provider":"deepseek","model_name":"deepseek-chat","temperature":0.7,"memory_enabled":true,"tools":["web_search"],"sub_agents":[],"permissions":{"can_read_web":true}}')
on conflict do nothing;

-- ============================================================================
-- Comments
-- ============================================================================
comment on table custom_agents is 'User-created AI agent configurations. Stores name, instructions, model, tools, and workflow settings. Agents produce recommendations only; dangerous actions require human approval.';
comment on table agent_tools is 'Tools available to each custom agent with permission levels, rate limits, and domain allowlists.';
comment on table knowledge_bases is 'Uploaded document collections turned into vector embeddings for RAG. Supports PDFs, docs, and website data.';
comment on table knowledge_base_chunks is 'Vector-embedded text chunks for semantic search. Requires pgvector extension.';
comment on table sub_agents is 'Specialist sub-agents that compose a multi-agent system under a parent agent.';
comment on table agent_threads is 'Persistent conversation threads between users and custom agents.';
comment on table agent_messages is 'Individual messages within agent conversation threads including tool calls and sub-agent outputs.';
comment on table agent_memories is 'Long-term memory entries with vector embeddings for semantic recall across conversations.';
comment on table custom_agent_runs is 'Execution records for custom agent runs with cost and performance tracking.';
comment on table custom_agent_run_steps is 'Fine-grained step tracking within an agent run covering planner, research, tool calls, and approval checks.';
comment on table agent_secrets is 'Encrypted API keys and credentials for agent tools. Only workspace owners and admins can manage.';
comment on table agent_templates is 'Pre-built agent configurations that users can clone to get started quickly.';