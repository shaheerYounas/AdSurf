import type { ProductProfile } from "@adsurf/types";
import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";
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
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/dashboard-summary`, {
    headers: localAuthHeaders(workspaceId),
    cache: "no-store",
    signal: init?.signal,
  });
  return readApiData<DashboardSummary>(response, "Dashboard summary could not be loaded.");
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
