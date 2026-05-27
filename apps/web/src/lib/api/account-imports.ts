import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type ReportDetection = {
  detected_report_type: string;
  confidence: "high" | "medium" | "low";
  required_columns_present: boolean;
  missing_columns: string[];
  available_entity_levels: string[];
  product_identifiers_available: string[];
};

export type AccountImportEntity = {
  id: string;
  entity_type: string;
  entity_key: string;
  product_id: string | null;
  asin: string | null;
  sku: string | null;
  product_name: string | null;
  campaign_name: string | null;
  ad_group_name: string | null;
  targeting: string | null;
  customer_search_term: string | null;
  resolution_status: string;
  metrics_json: Record<string, unknown>;
};

export type ProductMappingSuggestion = {
  id: string;
  asin: string | null;
  sku: string | null;
  detected_product_name: string | null;
  suggested_product_id: string | null;
  status: string;
};

export type AccountImportResponse = {
  import_record: {
    id: string;
    status: string;
    detected_report_type: string;
    detection_confidence: string;
    total_rows: number;
    processed_rows: number;
    error_rows: number;
  };
  detection: ReportDetection;
  entities: AccountImportEntity[];
  product_mapping_suggestions: ProductMappingSuggestion[];
};

export async function uploadAccountReport(file: File, workspaceId = defaultWorkspaceId): Promise<AccountImportResponse> {
  const initResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/init`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      original_filename: file.name,
      mime_type: file.type || "text/csv",
      file_size_bytes: file.size,
      source_type: "account_bulk_report",
    }),
  });
  const upload = await readApiData<{ upload_id: string; storage_path: string }>(initResponse, "Account report upload could not be initialized.");
  const objectResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${upload.upload_id}/object`, {
    method: "PUT",
    headers: localAuthHeaders(workspaceId, "analyst"),
    body: file,
  });
  await readApiData(objectResponse, "Account report file could not be stored.");
  const confirmResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${upload.upload_id}/confirm`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({}),
  });
  await readApiData(confirmResponse, "Account report upload could not be confirmed.");
  await fetch(`${apiBaseUrl}/v1/dev/process-upload-jobs`, {
    method: "POST",
    headers: localAuthHeaders(workspaceId, "admin"),
  }).catch(() => undefined);
  const importResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/account-imports`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: upload.upload_id }),
  });
  return readApiData<AccountImportResponse>(importResponse, "Account import could not be created.");
}
