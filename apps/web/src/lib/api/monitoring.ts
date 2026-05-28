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
  error_message?: string | null;
};

export type Recommendation = {
  id: string;
  product_id: string | null;
  monitoring_import_id?: string | null;
  account_import_id?: string | null;
  entity_key?: string | null;
  decision_source?: string | null;
  recommendation_type: string;
  entity_type: string;
  status: string;
  priority: string;
  confidence: string;
  rule_name: string;
  campaign_name: string | null;
  ad_group_name: string | null;
  targeting: string | null;
  customer_search_term: string | null;
  input_metrics_json: Record<string, string | number | null>;
  current_metric_snapshot_json: Record<string, string | number | null>;
  evidence_json: Record<string, unknown>;
  proposed_action_json: Record<string, unknown>;
  explanation_json: { summary?: string; approval_required?: boolean; decision_source?: string; ai_provider?: string; ai_model?: string; ai_final_decision?: boolean; execution_boundary?: string };
};

export type MonitoringSummary = {
  imports: MonitoringImport[];
  recommendation_counts: Record<string, number>;
  top_recommendations: Recommendation[];
  agent_summary: {
    headline?: string;
    dashboard_summary?: string;
    executive_summary?: string;
    analyst_notes?: string[];
    approver_notes?: string[];
    next_best_actions?: string[];
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

export async function getProductRecommendations(productId: string, workspaceId = defaultWorkspaceId): Promise<Recommendation[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/recommendations`, {
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

export async function runMonitoringAnalysis(importId: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/monitoring/imports/${importId}/run-analysis`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return readApiData<{ import_record: MonitoringImport; job_id?: string; job_created: boolean }>(response, "Monitoring analysis could not be queued.");
}

export async function runAccountImportAnalysis(accountImportId: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/account-imports/${accountImportId}/run-analysis`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return readApiData<{ account_import_id: string; status: string; run_count: number; recommendation_count: number; execution_boundary: string }>(response, "Account import analysis could not be completed.");
}
