import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type CompetitorUploadRecord = {
  id: string;
  workspace_id: string;
  product_id: string | null;
  original_filename: string;
  storage_path: string;
  mime_type: string;
  file_size_bytes: number;
  status: "queued" | "processing" | "succeeded" | "failed";
  row_count: number;
  cleaned_column_count: number;
  detected_columns_json: {
    original_column_name: string;
    normalized_column_name: string;
    column_index: number;
    is_search_volume: boolean;
    is_search_term: boolean;
    is_rank: boolean;
  }[];
  warnings_json: { code: string; message: string }[];
  error_message: string | null;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
};

export type CompetitorCleanedRow = {
  id: string;
  workspace_id: string;
  competitor_upload_id: string;
  row_number: number;
  search_term: string | null;
  search_volume: number | null;
  competitor_rank_values_json: {
    column_name: string;
    column_index: number;
    raw_value: string | null;
    numeric_value: string | null;
  }[];
  raw_metrics_json: Record<string, string | null> | null;
  relevance_score: number | null;
  scoring_status: string | null;
  rejection_reason: string | null;
  scored_at: string | null;
  created_at: string;
};

export type CompetitorUploadResponse = {
  upload: CompetitorUploadRecord;
  cleaned_rows: CompetitorCleanedRow[];
  total_rows: number;
  warnings: { code: string; message: string }[];
};

export type CompetitorUploadListResponse = {
  uploads: CompetitorUploadRecord[];
  total: number;
  meta: { total: number; page: number; page_size: number; has_next: boolean };
};

export type CompetitorVerificationResponse = {
  upload: CompetitorUploadRecord | null;
  verified_count: number;
  unverified_count: number;
  total_count: number;
  preview_rows: CompetitorCleanedRow[];
};

export type CampaignGenerationResponse = {
  upload: CompetitorUploadRecord;
  campaign_count: number;
  hero_campaign_name: string;
  group_count: number;
  bulk_export_preview: Record<string, string>[];
};

export type MonitoringDayResult = {
  day: number;
  date: string;
  spend: string;
  daily_budget: string;
  budget_consumed_pct: string;
  impressions: number;
  clicks: number;
  orders: number;
  sales: string;
  acos: string | null;
  action: string;
  previous_bid: string;
  suggested_bid: string;
  locked: boolean;
  day7_checkpoint: boolean;
};

export type CompetitorScoringResponse = {
  upload: CompetitorUploadRecord;
  total_rows: number;
  scored_rows: number;
  approved_count: number;
  rejected_count: number;
  error_count: number;
  preview_rows: CompetitorCleanedRow[];
};

export type CompetitorCleanedRowsResponse = {
  rows: CompetitorCleanedRow[];
  upload: CompetitorUploadRecord;
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
};

export async function uploadCompetitorCsv(
  file: File,
  workspaceId = defaultWorkspaceId,
): Promise<CompetitorUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId) },
    body: formData,
  });
  return readApiData<CompetitorUploadResponse>(response, "Competitor CSV upload failed.");
}

export async function getCompetitorUploads(
  workspaceId = defaultWorkspaceId,
): Promise<{ uploads: CompetitorUploadRecord[]; meta: { total: number; page: number; page_size: number; has_next: boolean } }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<CompetitorUploadRecord[]>(response, "Competitor uploads could not be loaded.").then((data) => ({
    uploads: data as unknown as CompetitorUploadRecord[],
    meta: { total: 0, page: 1, page_size: 20, has_next: false },
  }));
}

export async function getCompetitorUpload(
  uploadId: string,
  workspaceId = defaultWorkspaceId,
): Promise<CompetitorUploadRecord> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads/${uploadId}`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<CompetitorUploadRecord>(response, "Competitor upload could not be loaded.");
}

export async function scoreCompetitorUpload(
  uploadId: string,
  workspaceId = defaultWorkspaceId,
): Promise<CompetitorScoringResponse> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads/${uploadId}/score`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId) },
  });
  return readApiData<CompetitorScoringResponse>(response, "Competitor scoring failed.");
}

export async function verifyCompetitorKeywords(
  uploadId: string,
  competitors: string[],
  workspaceId = defaultWorkspaceId,
): Promise<CompetitorVerificationResponse> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads/${uploadId}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...localAuthHeaders(workspaceId) },
    body: JSON.stringify({ competitors }),
  });
  return readApiData<CompetitorVerificationResponse>(response, "Verification failed.");
}

export async function generateCampaignsFromVerified(
  uploadId: string,
  params: { product_id: string; product_name: string; batch_size?: number; daily_budget?: number; default_bid?: number },
  workspaceId = defaultWorkspaceId,
): Promise<CampaignGenerationResponse> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads/${uploadId}/generate-campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...localAuthHeaders(workspaceId) },
    body: JSON.stringify(params),
  });
  return readApiData<CampaignGenerationResponse>(response, "Campaign generation failed.");
}

export async function simulate14DayMonitoring(
  params: { product_id: string; campaign_name: string; daily_budget?: number; starting_bid?: number },
  workspaceId = defaultWorkspaceId,
): Promise<MonitoringDayResult[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/monitoring/14day-simulation`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...localAuthHeaders(workspaceId) },
    body: JSON.stringify(params),
  });
  return readApiData<MonitoringDayResult[]>(response, "14-day monitoring simulation failed.");
}

export async function getCompetitorCleanedRows(
  uploadId: string,
  page = 1,
  pageSize = 20,
  workspaceId = defaultWorkspaceId,
): Promise<CompetitorCleanedRowsResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-uploads/${uploadId}/rows?${params}`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<CompetitorCleanedRowsResponse>(response, "Cleaned rows could not be loaded.");
}