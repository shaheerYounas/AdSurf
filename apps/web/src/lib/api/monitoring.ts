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
  workspace_id?: string;
  product_id: string | null;
  monitoring_import_id?: string | null;
  snapshot_id?: string | null;
  account_import_id?: string | null;
  entity_key?: string | null;
  decision_source?: string | null;
  agent_run_id?: string | null;
  ai_run_id?: string | null;
  approval_boundary?: {
    requires_human_approval?: boolean;
    executes_live_amazon_change?: boolean;
    [key: string]: unknown;
  };
  recommendation_type: string;
  entity_type: string;
  status: string;
  priority: string;
  confidence: string;
  risk_level?: string | null;
  source?: string | null;
  evidence_score?: Record<string, unknown> | null;
  expected_impact?: Record<string, unknown> | null;
  rule_version_id?: string;
  rule_name: string;
  campaign_name: string | null;
  ad_group_name: string | null;
  targeting: string | null;
  customer_search_term: string | null;
  match_type?: string | null;
  current_bid?: string | number | null;
  recommended_bid?: string | number | null;
  change_percent?: string | number | null;
  current_budget?: string | number | null;
  recommended_budget?: string | number | null;
  input_metrics_json: Record<string, string | number | null>;
  current_metric_snapshot_json: Record<string, string | number | null>;
  evidence_json: Record<string, unknown>;
  proposed_action_json: Record<string, unknown>;
  explanation_json: {
    summary?: string;
    why_flagged?: string;
    evidence?: string;
    recommended_action?: string;
    risk?: string;
    approval_note?: string;
    advanced_details?: { rule?: unknown; thresholds?: unknown; source?: unknown; metric_snapshot?: unknown };
    approval_required?: boolean;
    decision_source?: string;
    ai_provider?: string;
    ai_model?: string;
    ai_final_decision?: boolean;
    execution_boundary?: string;
  };
  bulk_export_status?: string | null;
  learning_feedback_id?: string | null;
  previous_recommendation_id?: string | null;
  decided_by?: string | null;
  decision_note?: string | null;
  decided_at?: string | null;
  created_at?: string;
  updated_at?: string;
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
  summary_metrics: {
    rows_analyzed?: number;
    report_rows?: number;
    recommendations_generated?: number;
    pending_human_review?: number;
    actionable_recommendations?: number;
    watch_insights?: number;
    data_quality_checks?: number;
    budget_review_notes?: number;
    total_spend?: string;
    total_sales?: string;
    total_orders?: number;
    total_clicks?: number;
    total_impressions?: number;
    overall_acos?: string | null;
    zero_order_spend?: string;
    detected_products?: number;
    no_live_amazon_changes?: boolean;
    manual_export_required?: boolean;
  };
  action_recommendation_counts: Record<string, number>;
  non_action_insight_counts: Record<string, number>;
  issue_counts: Record<string, number>;
  detected_product_groups: Array<{
    key: string;
    asin?: string | null;
    sku?: string | null;
    rows: number;
    spend: string;
    sales: string;
    orders: number;
    campaign_count?: number;
    source?: string | null;
  }>;
};

// ── Request deduplication ──────────────────────────────────────────────
// Prevents duplicate in-flight requests for the same endpoint.
const _pendingRequests = new Map<string, Promise<any>>();

function deduplicate<T>(key: string, fn: () => Promise<T>): Promise<T> {
  if (_pendingRequests.has(key)) return _pendingRequests.get(key)!;
  const promise = fn().finally(() => _pendingRequests.delete(key));
  _pendingRequests.set(key, promise);
  return promise;
}

export async function createMonitoringImport(productId: string, uploadId: string, workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/monitoring-imports`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId }),
  });
  return readApiData<{ import_record: MonitoringImport; job_id?: string | null; already_imported?: boolean; message?: string | null }>(response, "Monitoring import could not be queued.");
}

export async function processMonitoringJobs(workspaceId = defaultWorkspaceId) {
  const response = await fetch(`${apiBaseUrl}/v1/dev/process-monitoring-jobs`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId),
  });
  return readApiData<{ processed: number }>(response, "Monitoring jobs could not be processed.");
}

export async function getProductMonitoring(productId: string, workspaceId = defaultWorkspaceId): Promise<MonitoringSummary> {
  return deduplicate(`monitoring:${productId}:${workspaceId}`, async () => {
    const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/monitoring`, {
      headers: localAuthHeaders(workspaceId),
    });
    return readApiData<MonitoringSummary>(response, "Monitoring summary could not be loaded.");
  });
}

export async function getRecommendations(workspaceId = defaultWorkspaceId): Promise<Recommendation[]> {
  return deduplicate(`recs:${workspaceId}`, async () => {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/recommendations`, {
        headers: localAuthHeaders(workspaceId),
        signal: controller.signal,
      });
      return readApiData<Recommendation[]>(response, "Recommendations could not be loaded.");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return [];
      throw error;
    } finally {
      globalThis.clearTimeout(timeout);
    }
  });
}

export async function getProductRecommendations(productId: string, workspaceId = defaultWorkspaceId): Promise<Recommendation[]> {
  return deduplicate(`recs:${productId}:${workspaceId}`, async () => {
    const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/recommendations`, {
      headers: localAuthHeaders(workspaceId),
    });
    return readApiData<Recommendation[]>(response, "Recommendations could not be loaded.");
  });
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
