import type { ProductProfile } from "@adsurf/types";
import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

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
