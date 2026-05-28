import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type WorkflowEvent = {
  id: string;
  workflow_id: string;
  workspace_id: string;
  agent_id: string | null;
  node_name: string;
  event_type: string;
  message: string;
  metadata_json: Record<string, unknown>;
  latency_ms: number | null;
  provider: string | null;
  model: string | null;
  created_at: string;
};

export type WorkflowSummary = {
  workflow: {
    id: string;
    workspace_id: string;
    account_import_id: string | null;
    upload_id: string | null;
    status: string;
    current_node: string | null;
    state_json: Record<string, unknown>;
  };
  progress: {
    current_node?: string;
    completed_steps?: number;
    total_steps?: number;
    percent?: number;
  };
  latest_events: WorkflowEvent[];
};

export async function getWorkflow(workflowId: string, workspaceId = defaultWorkspaceId): Promise<WorkflowSummary> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/workflows/${workflowId}`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<WorkflowSummary>(response, "Workflow status could not be loaded.");
}

export async function getWorkflowEvents(workflowId: string, workspaceId = defaultWorkspaceId): Promise<WorkflowEvent[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/workflows/${workflowId}/events`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<WorkflowEvent[]>(response, "Workflow events could not be loaded.");
}

export async function controlWorkflow(workflowId: string, action: "pause" | "resume" | "stop" | "rerun", reason: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/workflows/${workflowId}/${action}`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return readApiData<unknown>(response, `Workflow ${action} could not be saved.`);
}
