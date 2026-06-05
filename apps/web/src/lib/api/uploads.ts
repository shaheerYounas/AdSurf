import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type UploadRecord = {
  id: string;
  workspace_id: string;
  product_id: string;
  original_filename: string;
  storage_path: string;
  mime_type: string;
  file_size_bytes: number;
  status: string;
  source_type: string;
  created_at: string;
  updated_at: string;
  confirmed_at: string | null;
};

export type ParseRun = {
  id: string;
  status: string;
  parsed_rows_count: number;
  error_rows_count: number;
  total_rows: number;
  total_columns: number;
  selected_sheet_name: string | null;
  completed_at: string | null;
};

export async function getUploads({
  productId,
  workspaceId = defaultWorkspaceId,
}: {
  productId?: string;
  workspaceId?: string;
} = {}): Promise<UploadRecord[]> {
  const params = new URLSearchParams();
  if (productId) params.set("product_id", productId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads${suffix}`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<UploadRecord[]>(response, "Uploads could not be loaded.");
}

export async function getUploadParseRuns(uploadId: string, workspaceId = defaultWorkspaceId): Promise<ParseRun[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/parse-runs`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<ParseRun[]>(response, "Parse runs could not be loaded.");
}

export async function deleteUpload(uploadId: string, workspaceId = defaultWorkspaceId): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId),
  });
  await readApiData<unknown>(response, "Upload could not be deleted.");
}

export async function archiveUpload(uploadId: string, workspaceId = defaultWorkspaceId): Promise<UploadRecord> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/archive`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId),
  });
  return readApiData<UploadRecord>(response, "Upload could not be archived.");
}

export async function reprocessUpload(uploadId: string, workspaceId = defaultWorkspaceId): Promise<{ upload: UploadRecord; job_id: string }> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/reprocess`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId),
  });
  return readApiData<{ upload: UploadRecord; job_id: string }>(response, "Upload could not be reprocessed.");
}
