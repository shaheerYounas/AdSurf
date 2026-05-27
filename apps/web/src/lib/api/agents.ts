import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type AgentDefinition = {
  agent_id: string;
  display_name: string;
  description: string;
  task_type: string;
  enabled_by_default: boolean;
  allowed_actions: string[];
  input_dependencies: string[];
  output_type: string;
  can_mutate_live_amazon_ads: boolean;
};

export type AgentConfig = {
  workspace_id: string;
  product_id: string | null;
  agent_id: string;
  enabled: boolean;
  mode: "deterministic" | "ai" | "hybrid";
  strictness_level: "conservative" | "balanced" | "aggressive";
  confidence_threshold: "low" | "medium" | "high";
  max_recommendations: number;
  allow_bid_recommendations: boolean;
  allow_negative_keyword_recommendations: boolean;
  allow_pause_recommendations: boolean;
  allow_budget_recommendations: boolean;
};

export type AgentRun = {
  id: string;
  workspace_id: string;
  product_id: string | null;
  monitoring_import_id: string | null;
  agent_id: string;
  agent_name: string;
  provider: string;
  model: string;
  schema_version: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_json: Record<string, unknown>;
  status: string;
  latency_ms: number;
  mode: string | null;
  strictness_level: string | null;
  confidence_threshold: string | null;
  recommendation_ids: string[];
  created_at: string;
  controlled_by: string | null;
  control_reason: string | null;
  can_mutate_live_amazon_ads: boolean;
};

export type AgentEvent = {
  id: string;
  agent_id: string;
  agent_run_id: string | null;
  monitoring_import_id: string | null;
  event_type: string;
  message: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AgentWorkflow = {
  monitoring_import_id: string;
  nodes: Array<{
    agent_id: string;
    display_name: string;
    description: string;
    status: string;
    mode: string;
    strictness_level: string;
    last_run_at: string | null;
    recommendations_created: number;
    errors: string[];
    can_mutate_live_amazon_ads: boolean;
  }>;
  edges: Array<{
    source_agent_id: string;
    target_agent_id: string;
    status: string;
    data_passed_summary: string[];
    created_at: string | null;
    completed_at: string | null;
  }>;
  events: AgentEvent[];
};

export async function getAgents(workspaceId = defaultWorkspaceId): Promise<AgentDefinition[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agents`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentDefinition[]>(response, "Agents could not be loaded.");
}

export async function getAgentConfigs(workspaceId = defaultWorkspaceId, productId?: string): Promise<AgentConfig[]> {
  const suffix = productId ? `?product_id=${productId}` : "";
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agent-configs${suffix}`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentConfig[]>(response, "Agent configuration could not be loaded.");
}

export async function updateAgentConfig(agentId: string, payload: Partial<AgentConfig> & { reason: string }, workspaceId = defaultWorkspaceId): Promise<AgentConfig> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agent-configs/${agentId}`, {
    method: "PATCH",
    headers: { ...localAuthHeaders(workspaceId, "admin"), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<AgentConfig>(response, "Agent configuration could not be saved.");
}

export async function getAgentRuns(workspaceId = defaultWorkspaceId, monitoringImportId?: string): Promise<AgentRun[]> {
  const suffix = monitoringImportId ? `?monitoring_import_id=${monitoringImportId}` : "";
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agent-runs${suffix}`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentRun[]>(response, "Agent runs could not be loaded.");
}

export async function getAgentWorkflow(importId: string, workspaceId = defaultWorkspaceId): Promise<AgentWorkflow> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/monitoring/imports/${importId}/agent-workflow`, { headers: localAuthHeaders(workspaceId), cache: "no-store" });
  return readApiData<AgentWorkflow>(response, "Agent workflow could not be loaded.");
}

export async function controlAgentRun(runId: string, action: "pause" | "resume" | "stop" | "rerun", reason: string, workspaceId = defaultWorkspaceId): Promise<AgentRun> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/agent-runs/${runId}/${action}`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return readApiData<AgentRun>(response, "Agent control action could not be saved.");
}

export async function rerunFromAgent(importId: string, agentId: string, reason: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/monitoring/imports/${importId}/rerun-from-agent/${agentId}`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return readApiData<{ monitoring_import_id: string; agent_id: string; status: string }>(response, "Agent workflow rerun could not be queued.");
}
