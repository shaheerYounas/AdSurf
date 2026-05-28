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
  try {
    options.onProgress?.("initializing_upload", "Creating upload and workflow records.");
    const form = new FormData();
    form.append("file", file);
    options.onProgress?.("storing_file", `Uploading ${file.name}.`);
    const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/report`, {
      method: "POST",
      headers: localAuthHeaders(workspaceId, "analyst"),
      body: form,
    });
    options.onProgress?.("creating_account_import", "Creating account import and starting workflow.");
    return readApiData<AccountImportResponse>(response, "Account report upload could not be completed.");
  } catch (err) {
    if (err instanceof TypeError && err.message === "Failed to fetch") {
      throw new Error("Unable to connect to the server. Please ensure the API is running.");
    }
    throw err;
  }
}
