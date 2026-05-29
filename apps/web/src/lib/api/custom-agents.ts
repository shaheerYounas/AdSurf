import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

// ── Types ────────────────────────────────────────────────────────────────────

export type CustomAgentSummary = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  model_provider: string;
  model_name: string;
  memory_enabled: boolean;
  status: "draft" | "active" | "paused" | "archived";
  created_at: string;
  updated_at: string;
  tool_count: number;
  sub_agent_count: number;
  thread_count: number;
};

export type CustomAgent = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  role_instructions: string | null;
  model_provider: "openai" | "anthropic" | "deepseek" | "google" | "local";
  model_name: string;
  temperature: number;
  max_tokens: number;
  memory_enabled: boolean;
  memory_ttl_days: number;
  output_format: "text" | "json" | "markdown" | "table" | "code" | "email";
  output_schema: Record<string, unknown> | null;
  workflow_type: "sequential" | "parallel" | "supervisor" | "custom";
  workflow_graph: Record<string, unknown> | null;
  status: "draft" | "active" | "paused" | "archived";
  metadata_json: Record<string, unknown>;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  tools: AgentTool[];
  sub_agents: SubAgent[];
  knowledge_base_ids: string[];
};

export type AgentTool = {
  id: string;
  workspace_id: string;
  agent_id: string;
  tool_name: string;
  tool_config: Record<string, unknown>;
  enabled: boolean;
  permission_level: "read" | "write" | "execute" | "admin";
  requires_approval: boolean;
  rate_limit_per_day: number | null;
  allowed_domains: string[] | null;
  allowed_actions: string[] | null;
  created_at: string;
  updated_at: string;
};

export type AvailableTool = {
  tool_name: string;
  display_name: string;
  description: string;
  category: string;
  default_permission_level: "read" | "write" | "execute" | "admin";
  requires_approval_by_default: boolean;
  is_dangerous: boolean;
};

export type KnowledgeBase = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  source_type: string;
  embedding_model: string;
  embedding_provider: string;
  file_count: number;
  chunk_count: number;
  status: "pending" | "processing" | "ready" | "error";
  created_by: string | null;
  created_at: string;
  updated_at: string;
  files: KnowledgeBaseFile[];
};

export type KnowledgeBaseFile = {
  id: string;
  knowledge_base_id: string;
  file_name: string;
  file_path: string;
  file_type: string;
  file_size_bytes: number | null;
  chunk_count: number;
  status: string;
  error_message: string | null;
  created_at: string;
};

export type SubAgent = {
  id: string;
  workspace_id: string;
  parent_agent_id: string;
  name: string;
  role: string;
  instructions: string;
  model_provider: string | null;
  model_name: string | null;
  tools_json: string[];
  execution_order: number;
  enabled: boolean;
  requires_approval: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentThread = {
  id: string;
  workspace_id: string;
  agent_id: string;
  title: string | null;
  status: string;
  metadata_json: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_at: string | null;
};

export type AgentMessage = {
  id: string;
  workspace_id: string;
  thread_id: string;
  agent_id: string | null;
  role: "user" | "assistant" | "system" | "tool" | "sub_agent";
  content: string | null;
  tool_calls_json: Record<string, unknown>[] | null;
  tool_call_id: string | null;
  sub_agent_name: string | null;
  token_count: number | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AgentMemory = {
  id: string;
  workspace_id: string;
  agent_id: string;
  thread_id: string | null;
  memory_type: "preference" | "fact" | "decision" | "context" | "user_info" | "project";
  content: string;
  importance: number;
  access_count: number;
  last_accessed_at: string | null;
  expires_at: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AgentRun = {
  id: string;
  workspace_id: string;
  agent_id: string;
  thread_id: string | null;
  status: string;
  model_provider: string | null;
  model_name: string | null;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_json: Record<string, unknown>;
  tokens_input: number;
  tokens_output: number;
  cost_usd: number;
  latency_ms: number | null;
  sub_agent_runs_json: Record<string, unknown>[];
  tool_call_count: number;
  knowledge_chunks_retrieved: number;
  metadata_json: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  steps: AgentRunStep[];
};

export type AgentRunStep = {
  id: string;
  workspace_id: string;
  run_id: string;
  agent_name: string | null;
  step_type: string;
  step_order: number;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  status: string;
  error_message: string | null;
  latency_ms: number | null;
  created_at: string;
  completed_at: string | null;
};

export type AgentTemplate = {
  id: string;
  name: string;
  description: string;
  category: string;
  config_json: Record<string, unknown>;
  is_public: boolean;
  usage_count: number;
  created_at: string;
};

// ── Tools Catalog ────────────────────────────────────────────────────────────

export async function getAvailableTools(workspaceId = defaultWorkspaceId): Promise<AvailableTool[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agent-tools-catalog`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AvailableTool[]>(response, "Available tools could not be loaded.");
}

// ── Custom Agents CRUD ───────────────────────────────────────────────────────

export async function listCustomAgents(workspaceId = defaultWorkspaceId): Promise<CustomAgentSummary[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<CustomAgentSummary[]>(response, "Custom agents could not be loaded.");
}

export async function getCustomAgent(agentId: string, workspaceId = defaultWorkspaceId): Promise<CustomAgent> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<CustomAgent>(response, "Custom agent could not be loaded.");
}

export async function createCustomAgent(payload: Partial<CustomAgent> & { name: string }, workspaceId = defaultWorkspaceId): Promise<CustomAgent> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<CustomAgent>(response, "Custom agent could not be created.");
}

export async function updateCustomAgent(agentId: string, payload: Partial<CustomAgent>, workspaceId = defaultWorkspaceId): Promise<CustomAgent> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}`, {
    method: "PATCH",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<CustomAgent>(response, "Custom agent could not be updated.");
}

export async function deleteCustomAgent(agentId: string, workspaceId = defaultWorkspaceId): Promise<{ id: string; deleted: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ id: string; deleted: boolean }>(response, "Custom agent could not be deleted.");
}

// ── Agent Tools ──────────────────────────────────────────────────────────────

export async function listAgentTools(agentId: string, workspaceId = defaultWorkspaceId): Promise<AgentTool[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/tools`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentTool[]>(response, "Agent tools could not be loaded.");
}

export async function addAgentTool(agentId: string, payload: Partial<AgentTool> & { tool_name: string }, workspaceId = defaultWorkspaceId): Promise<AgentTool> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/tools`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<AgentTool>(response, "Tool could not be added.");
}

export async function updateAgentTool(agentId: string, toolId: string, payload: Partial<AgentTool>, workspaceId = defaultWorkspaceId): Promise<AgentTool> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/tools/${toolId}`, {
    method: "PATCH",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<AgentTool>(response, "Tool could not be updated.");
}

export async function removeAgentTool(agentId: string, toolId: string, workspaceId = defaultWorkspaceId): Promise<{ id: string; deleted: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/tools/${toolId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ id: string; deleted: boolean }>(response, "Tool could not be removed.");
}

// ── Knowledge Bases ──────────────────────────────────────────────────────────

export async function listKnowledgeBases(workspaceId = defaultWorkspaceId): Promise<KnowledgeBase[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/knowledge-bases`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<KnowledgeBase[]>(response, "Knowledge bases could not be loaded.");
}

export async function createKnowledgeBase(payload: { name: string; description?: string }, workspaceId = defaultWorkspaceId): Promise<KnowledgeBase> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/knowledge-bases`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<KnowledgeBase>(response, "Knowledge base could not be created.");
}

export async function deleteKnowledgeBase(kbId: string, workspaceId = defaultWorkspaceId): Promise<{ id: string; deleted: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/knowledge-bases/${kbId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ id: string; deleted: boolean }>(response, "Knowledge base could not be deleted.");
}

// ── Knowledge Base Links ─────────────────────────────────────────────────────

export async function linkKnowledgeBase(agentId: string, kbId: string, workspaceId = defaultWorkspaceId): Promise<{ agent_id: string; knowledge_base_id: string; linked: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/knowledge-bases/${kbId}`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ agent_id: string; knowledge_base_id: string; linked: boolean }>(response, "Knowledge base could not be linked.");
}

export async function unlinkKnowledgeBase(agentId: string, kbId: string, workspaceId = defaultWorkspaceId): Promise<{ agent_id: string; knowledge_base_id: string; linked: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/knowledge-bases/${kbId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ agent_id: string; knowledge_base_id: string; linked: boolean }>(response, "Knowledge base could not be unlinked.");
}

// ── Sub-Agents ───────────────────────────────────────────────────────────────

export async function listSubAgents(agentId: string, workspaceId = defaultWorkspaceId): Promise<SubAgent[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/sub-agents`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<SubAgent[]>(response, "Sub-agents could not be loaded.");
}

export async function createSubAgent(agentId: string, payload: { name: string; role: string; instructions: string; execution_order?: number }, workspaceId = defaultWorkspaceId): Promise<SubAgent> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/sub-agents`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<SubAgent>(response, "Sub-agent could not be created.");
}

export async function updateSubAgent(agentId: string, subAgentId: string, payload: Partial<SubAgent>, workspaceId = defaultWorkspaceId): Promise<SubAgent> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/sub-agents/${subAgentId}`, {
    method: "PATCH",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<SubAgent>(response, "Sub-agent could not be updated.");
}

export async function deleteSubAgent(agentId: string, subAgentId: string, workspaceId = defaultWorkspaceId): Promise<{ id: string; deleted: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/sub-agents/${subAgentId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ id: string; deleted: boolean }>(response, "Sub-agent could not be deleted.");
}

// ── Threads & Messages ──────────────────────────────────────────────────────

export async function listAgentThreads(agentId: string, workspaceId = defaultWorkspaceId): Promise<AgentThread[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/threads`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentThread[]>(response, "Threads could not be loaded.");
}

export async function createAgentThread(agentId: string, title?: string, workspaceId = defaultWorkspaceId): Promise<AgentThread> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/threads`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId, title: title || null }),
  });
  return readApiData<AgentThread>(response, "Thread could not be created.");
}

export async function listThreadMessages(threadId: string, workspaceId = defaultWorkspaceId): Promise<AgentMessage[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/threads/${threadId}/messages`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentMessage[]>(response, "Messages could not be loaded.");
}

export async function runAgent(agentId: string, message: string, threadId?: string, workspaceId = defaultWorkspaceId): Promise<AgentRun> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/run`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId || null }),
  });
  return readApiData<AgentRun>(response, "Agent run could not be started.");
}

export async function getAgentRun(runId: string, workspaceId = defaultWorkspaceId): Promise<AgentRun> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agent-runs/${runId}`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentRun>(response, "Agent run could not be loaded.");
}

// ── Memories ────────────────────────────────────────────────────────────────

export async function listAgentMemories(agentId: string, workspaceId = defaultWorkspaceId): Promise<AgentMemory[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/memories`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentMemory[]>(response, "Memories could not be loaded.");
}

export async function createAgentMemory(agentId: string, payload: { content: string; memory_type: string; importance?: number }, workspaceId = defaultWorkspaceId): Promise<AgentMemory> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/memories`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<AgentMemory>(response, "Memory could not be created.");
}

export async function deleteAgentMemory(agentId: string, memoryId: string, workspaceId = defaultWorkspaceId): Promise<{ id: string; deleted: boolean }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/custom-agents/${agentId}/memories/${memoryId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<{ id: string; deleted: boolean }>(response, "Memory could not be deleted.");
}

// ── Templates ───────────────────────────────────────────────────────────────

export async function listAgentTemplates(workspaceId = defaultWorkspaceId): Promise<AgentTemplate[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agent-templates`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentTemplate[]>(response, "Templates could not be loaded.");
}

export async function cloneAgentTemplate(templateId: string, workspaceId = defaultWorkspaceId): Promise<CustomAgent> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agent-templates/${templateId}/clone`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId, "analyst"),
  });
  return readApiData<CustomAgent>(response, "Template could not be cloned.");
}