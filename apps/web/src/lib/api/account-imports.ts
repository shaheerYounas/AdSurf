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
    upload_id?: string;
    parse_run_id?: string;
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
  workflow_id?: string | null;
};

export type UploadAccountReportProgress =
  | "initializing_upload"
  | "storing_file"
  | "confirming_upload"
  | "processing_file"
  | "creating_account_import";

export type UploadAccountReportOptions = {
  onProgress?: (step: UploadAccountReportProgress, detail?: string) => void;
};

export async function uploadAccountReport(file: File, workspaceId = defaultWorkspaceId, options: UploadAccountReportOptions = {}): Promise<AccountImportResponse> {
  let upload;
  try {
    options.onProgress?.("initializing_upload", "Creating upload record.");
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
    upload = await readApiData<{ upload_id: string; storage_path: string }>(initResponse, "Account report upload could not be initialized.");
  } catch (err) {
    if (err instanceof TypeError && err.message === "Failed to fetch") {
      throw new Error("Unable to connect to the server. Please ensure the API is running.");
    }
    throw err;
  }
  
  try {
    options.onProgress?.("storing_file", `Writing file bytes for upload ${upload.upload_id}.`);
    const objectResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${upload.upload_id}/object`, {
      method: "PUT",
      headers: localAuthHeaders(workspaceId, "analyst"),
      body: file,
    });
    await readApiData(objectResponse, "Account report file could not be stored.");
    
    options.onProgress?.("confirming_upload", `Queueing parser job for upload ${upload.upload_id}.`);
    const confirmResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${upload.upload_id}/confirm`, {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({}),
    });
    await readApiData(confirmResponse, "Account report upload could not be confirmed.");
    
    options.onProgress?.("processing_file", "Processing upload rows.");
    const processResponse = await fetch(`${apiBaseUrl}/v1/dev/process-upload-jobs`, {
      method: "POST",
      headers: localAuthHeaders(workspaceId, "admin"),
    });
    await readApiData(processResponse, "Upload was queued, but local upload processing did not complete. Start the upload worker or enable the local dev worker endpoint.");
    
    options.onProgress?.("creating_account_import", `Creating account import from upload ${upload.upload_id}.`);
    const importResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/account-imports`, {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId, "analyst"), "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: upload.upload_id }),
    });
    return readApiData<AccountImportResponse>(importResponse, "Account import could not be created.");
  } catch (err) {
    if (err instanceof TypeError && err.message === "Failed to fetch") {
      throw new Error("Unable to connect to the server during upload. Please ensure the API is running.");
    }
    throw err;
  }
}
