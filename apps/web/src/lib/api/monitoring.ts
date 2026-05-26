import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type MonitoringImport = {
  id: string;
  product_id: string;
  upload_id: string;
  status: string;
  report_type: string;
  total_rows: number;
  processed_rows: number;
  error_rows: number;
  date_range_start: string | null;
  date_range_end: string | null;
  data_quality_warnings_json: Array<Record<string, unknown>>;
};

export type Recommendation = {
  id: string;
  product_id: string;
  recommendation_type: string;
  status: string;
  priority: string;
  rule_name: string;
  campaign_name: string;
  ad_group_name: string;
  targeting: string;
  customer_search_term: string;
  input_metrics_json: Record<string, string | number | null>;
  proposed_action_json: Record<string, string | boolean | null>;
  explanation_json: { summary?: string; approval_required?: boolean; execution_boundary?: string };
};

export type MonitoringSummary = {
  imports: MonitoringImport[];
  recommendation_counts: Record<string, number>;
  top_recommendations: Recommendation[];
  agent_summary: {
    headline?: string;
    stakeholder_note?: string;
    next_step?: string;
    total_spend?: string;
    total_sales?: string;
    total_orders?: number;
  } | null;
};

export async function createMonitoringImport(productId: string, uploadId: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/monitoring-imports`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId }),
  });
  return readApiData<{ import_record: MonitoringImport; job_id: string }>(response, "Monitoring import could not be queued.");
}

export async function processMonitoringJobs(workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/dev/process-monitoring-jobs`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId),
  });
  return readApiData<{ processed: number }>(response, "Monitoring jobs could not be processed.");
}

export async function getProductMonitoring(productId: string, workspaceId = defaultWorkspaceId): Promise<MonitoringSummary> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/monitoring`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<MonitoringSummary>(response, "Monitoring summary could not be loaded.");
}

export async function getRecommendations(workspaceId = defaultWorkspaceId): Promise<Recommendation[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/recommendations`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<Recommendation[]>(response, "Recommendations could not be loaded.");
}

export async function decideRecommendation(recommendationId: string, decision: "approve" | "reject", note: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/recommendations/${recommendationId}/${decision}`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  return readApiData<Recommendation>(response, "Recommendation decision could not be saved.");
}
