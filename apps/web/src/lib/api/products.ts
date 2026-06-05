import type { ProductProfile } from "@adsurf/types";
import { apiBaseUrl, defaultWorkspaceId, fetchApiData, localAuthHeaders, readApiData } from "@/lib/api/client";
import type { Recommendation } from "@/lib/api/monitoring";

export type ProductProfileCreate = {
  product_name: string;
  asin?: string | null;
  sku?: string | null;
  marketplace: string;
  currency: string;
  target_acos: string;
  default_budget: string;
  default_bid: string;
};

export function getDefaultWorkspaceId() {
  return defaultWorkspaceId;
}

export type DashboardSummary = {
  products: ProductProfile[];
  product_count: number;
  upload_count: number;
  upload_counts: Record<string, number>;
  pending_recommendation_count: number;
  recommendation_counts: Record<string, number>;
  top_recommendations: Recommendation[];
};

export async function getDashboardSummary(workspaceId = defaultWorkspaceId, init?: Pick<RequestInit, "signal">): Promise<DashboardSummary> {
  return fetchApiData<DashboardSummary>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/dashboard-summary`,
    {
      headers: localAuthHeaders(workspaceId),
      cache: "no-store",
      signal: init?.signal,
    },
    "Dashboard summary could not be loaded.",
  );
}

export async function getProductProfiles(workspaceId = defaultWorkspaceId): Promise<ProductProfile[]> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<ProductProfile[]>(response, "Product profiles could not be loaded.");
}

export async function getProductProfile(productId: string, workspaceId = defaultWorkspaceId): Promise<ProductProfile> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
  });
  return readApiData<ProductProfile>(response, "Product profile could not be loaded.");
}

export async function createProductProfile(payload: ProductProfileCreate, workspaceId = defaultWorkspaceId): Promise<ProductProfile> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiData<ProductProfile>(response, "Product profile could not be saved.");
}

export async function deleteProductProfile(productId: string, workspaceId = defaultWorkspaceId): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}`, {
    method: "DELETE",
    headers: localAuthHeaders(workspaceId),
  });
  await readApiData<{ deleted: boolean }>(response, "Product profile could not be deleted.");
}

export async function bulkDeleteProductProfiles(productIds: string[], workspaceId = defaultWorkspaceId): Promise<{ deleted_count: number }> {
  return fetchApiData<{ deleted_count: number }>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/products/bulk-delete`,
    {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
      body: JSON.stringify({ product_ids: productIds }),
    },
    "Products could not be deleted.",
  );
}

// ─── Bulk import types ─────────────────────────────────────────────────────────

export type BulkImportStatus =
  | "parsing"
  | "validating"
  | "ready_for_review"
  | "creating"
  | "completed"
  | "failed"
  | "cancelled";

export type BulkImportRowStatus =
  | "valid"
  | "invalid"
  | "duplicate_in_file"
  | "already_exists"
  | "skipped"
  | "created"
  | "updated"
  | "failed";

export type BulkImportConflictStrategy =
  | "skip_existing"
  | "update_existing"
  | "create_only_missing";

export interface BulkProductRowValidationError {
  field: string;
  message: string;
  raw_value?: string;
}

export interface BulkProductRow {
  id: string;
  row_number: number;
  status: BulkImportRowStatus;
  product_name?: string;
  asin?: string;
  sku?: string;
  marketplace?: string;
  currency?: string;
  target_acos?: string;
  default_budget?: string;
  default_bid?: string;
  brand?: string;
  category?: string;
  notes?: string;
  product_id?: string;
  validation_errors: BulkProductRowValidationError[];
  raw_row_json: Record<string, string>;
}

export interface BulkProductImportSummary {
  import_id: string;
  status: BulkImportStatus;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_in_file_rows: number;
  already_exists_rows: number;
  rows_needing_review: number;
  exportable_valid_rows: number;
  rows_to_create: number;
  rows_to_update: number;
  rows_to_skip: number;
  warning_rows: number;
  detected_columns: Record<string, string>;
  exception_rows: BulkProductRow[];
}

export interface BulkProductImport {
  id: string;
  workspace_id: string;
  original_filename: string;
  file_hash?: string;
  status: BulkImportStatus;
  conflict_strategy: BulkImportConflictStrategy;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_in_file_rows: number;
  already_exists_rows: number;
  created_rows: number;
  updated_rows: number;
  skipped_rows: number;
  failed_rows: number;
  detected_columns_json: Record<string, string>;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface BulkProductImportWithRows extends BulkProductImport {
  rows: BulkProductRow[];
}

export interface BulkImportCommitResult {
  import_id: string;
  status: BulkImportStatus;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  failed_count: number;
  created_product_ids: string[];
  updated_product_ids: string[];
}

// ─── Competitor research types ─────────────────────────────────────────────────

export type CompetitorResearchStatus =
  | "queued"
  | "running"
  | "paused_manual_verification"
  | "succeeded"
  | "failed"
  | "cancelled";

export type CompetitorKeywordStatus = "queued" | "running" | "succeeded" | "failed" | "skipped";

export interface CompetitorResearchRunSettings {
  marketplace?: string;
  max_keywords_per_run?: number;
  max_competitors_per_keyword?: number;
  delay_min_seconds?: number;
  delay_max_seconds?: number;
  open_product_detail_pages?: boolean;
  headless?: boolean;
}

export interface CompetitorResearchCreateRequest {
  product_id?: string;
  settings?: CompetitorResearchRunSettings;
  seed_keywords?: string[];
  manual_keywords?: string[];
  include_high_spend_terms?: boolean;
  include_move_to_exact_terms?: boolean;
}

export interface CompetitorResearchKeyword {
  id: string;
  run_id: string;
  keyword: string;
  keyword_source?: string;
  priority_rank: number;
  status: CompetitorKeywordStatus;
  search_url?: string;
  searched_at?: string;
  screenshot_path?: string;
  organic_count?: number;
  sponsored_count?: number;
  error_message?: string;
}

export interface CompetitorResearchResult {
  id: string;
  run_id: string;
  keyword_id: string;
  position: number;
  result_type: "organic" | "sponsored";
  asin?: string;
  title?: string;
  brand?: string;
  price_text?: string;
  price_usd?: number;
  rating?: number;
  review_count?: number;
  has_coupon?: boolean;
  is_prime?: boolean;
  is_amazon_choice?: boolean;
  is_best_seller?: boolean;
  image_url?: string;
  product_url?: string;
}

export interface CompetitorAiInsight {
  id: string;
  run_id: string;
  keyword_id: string;
  keyword: string;
  opportunity_score?: number;
  competitor_strength_score?: number;
  relevance_score?: number;
  risk_score?: number;
  competitor_strength?: string;
  sponsored_intensity?: string;
  organic_difficulty?: string;
  product_market_fit?: string;
  avg_price_range?: string;
  avg_review_count?: string;
  avg_price_min_usd?: number;
  avg_price_max_usd?: number;
  avg_review_count_number?: number;
  recommended_ad_strategy?: string;
  listing_improvement?: string;
  action_recommendation?: string;
  full_summary?: string;
  ai_provider?: string;
  ai_model?: string;
  generated_at: string;
}

export interface CompetitorResearchRun {
  id: string;
  workspace_id: string;
  product_id?: string;
  marketplace: string;
  max_keywords_per_run: number;
  max_competitors_per_keyword: number;
  delay_min_seconds: number;
  delay_max_seconds: number;
  open_product_detail_pages: boolean;
  headless: boolean;
  status: CompetitorResearchStatus;
  keywords_total: number;
  keywords_completed: number;
  keywords_failed: number;
  products_captured: number;
  paused_reason?: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface CompetitorResearchRunDetail extends CompetitorResearchRun {
  keywords: CompetitorResearchKeyword[];
  insights: CompetitorAiInsight[];
}

export interface CompetitorResearchStartResult {
  run: CompetitorResearchRun;
  paused_for_verification: boolean;
  safety_note: string;
}

// ─── Bulk import API ───────────────────────────────────────────────────────────

/**
 * Upload a CSV/XLSX file and receive a validation summary.
 * Products are NOT created yet — this is step 1 of the import flow.
 */
export async function uploadBulkProductFile(
  file: File,
  options: {
    workspaceId?: string;
    conflictStrategy?: BulkImportConflictStrategy;
    workspaceDefaultAcos?: number;
    workspaceDefaultBudget?: number;
    workspaceDefaultBid?: number;
  } = {}
): Promise<BulkProductImportSummary> {
  const workspaceId = options.workspaceId ?? defaultWorkspaceId;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("conflict_strategy", options.conflictStrategy ?? "skip_existing");
  if (options.workspaceDefaultAcos !== undefined) {
    formData.append("workspace_default_acos", String(options.workspaceDefaultAcos));
  }
  if (options.workspaceDefaultBudget !== undefined) {
    formData.append("workspace_default_budget", String(options.workspaceDefaultBudget));
  }
  if (options.workspaceDefaultBid !== undefined) {
    formData.append("workspace_default_bid", String(options.workspaceDefaultBid));
  }

  return fetchApiData<BulkProductImportSummary>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/products/bulk-import`,
    {
      method: "POST",
      headers: localAuthHeaders(workspaceId),
      body: formData,
    },
    "Failed to upload product file."
  );
}

/** Retrieve a bulk import record with all rows (for the review step). */
export async function getBulkProductImport(
  importId: string,
  workspaceId = defaultWorkspaceId
): Promise<BulkProductImportWithRows> {
  return fetchApiData<BulkProductImportWithRows>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/products/bulk-import/${importId}`,
    { headers: localAuthHeaders(workspaceId) },
    "Failed to load import details."
  );
}

/**
 * Commit a validated import — create product profiles for all valid rows.
 * No products are created until this is called.
 */
export async function commitBulkProductImport(
  importId: string,
  options: { workspaceId?: string; conflictStrategy?: BulkImportConflictStrategy } = {}
): Promise<BulkImportCommitResult> {
  const workspaceId = options.workspaceId ?? defaultWorkspaceId;
  return fetchApiData<BulkImportCommitResult>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/products/bulk-import/${importId}/commit`,
    {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
      body: JSON.stringify({ conflict_strategy: options.conflictStrategy ?? "skip_existing" }),
    },
    "Failed to commit bulk import."
  );
}

/** List recent bulk imports for a workspace. */
export async function listBulkProductImports(
  workspaceId = defaultWorkspaceId
): Promise<BulkProductImport[]> {
  return fetchApiData<BulkProductImport[]>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/products/bulk-import`,
    { headers: localAuthHeaders(workspaceId) },
    "Failed to load import history."
  );
}

// ─── Competitor research API ───────────────────────────────────────────────────

/** Create a new competitor research run (keyword queue only — browser not started). */
export async function createCompetitorResearchRun(
  payload: CompetitorResearchCreateRequest,
  workspaceId = defaultWorkspaceId
): Promise<CompetitorResearchRun> {
  return fetchApiData<CompetitorResearchRun>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research`,
    {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to create competitor research run."
  );
}

/**
 * Start (or resume) a research run.
 * Opens a VISIBLE browser. If Amazon shows a CAPTCHA, the run pauses — never bypassed.
 */
export async function startCompetitorResearchRun(
  runId: string,
  workspaceId = defaultWorkspaceId
): Promise<CompetitorResearchStartResult> {
  return fetchApiData<CompetitorResearchStartResult>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research/${runId}/start`,
    {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    },
    "Failed to start competitor research run."
  );
}

/** Pause, resume, or cancel a run. */
export async function controlCompetitorResearchRun(
  runId: string,
  action: "pause" | "resume" | "cancel",
  reason?: string,
  workspaceId = defaultWorkspaceId
): Promise<CompetitorResearchRun> {
  return fetchApiData<CompetitorResearchRun>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research/${runId}/control`,
    {
      method: "POST",
      headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
      body: JSON.stringify({ action, reason }),
    },
    "Failed to update run status."
  );
}

/** Get full run detail including keyword queue and AI insights. */
export async function getCompetitorResearchRun(
  runId: string,
  workspaceId = defaultWorkspaceId
): Promise<CompetitorResearchRunDetail> {
  return fetchApiData<CompetitorResearchRunDetail>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research/${runId}`,
    { headers: localAuthHeaders(workspaceId) },
    "Failed to load competitor research run."
  );
}

/** List all runs for a workspace. */
export async function listCompetitorResearchRuns(
  workspaceId = defaultWorkspaceId
): Promise<CompetitorResearchRun[]> {
  return fetchApiData<CompetitorResearchRun[]>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research`,
    { headers: localAuthHeaders(workspaceId) },
    "Failed to load competitor research runs."
  );
}

/** Get competitor product results captured during a run. */
export async function getCompetitorResearchResults(
  runId: string,
  workspaceId = defaultWorkspaceId
): Promise<CompetitorResearchResult[]> {
  return fetchApiData<CompetitorResearchResult[]>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research/${runId}/results`,
    { headers: localAuthHeaders(workspaceId) },
    "Failed to load competitor results."
  );
}

/** Get AI insights for a run. */
export async function getCompetitorResearchInsights(
  runId: string,
  workspaceId = defaultWorkspaceId
): Promise<CompetitorAiInsight[]> {
  return fetchApiData<CompetitorAiInsight[]>(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/competitor-research/${runId}/insights`,
    { headers: localAuthHeaders(workspaceId) },
    "Failed to load competitor insights."
  );
}
