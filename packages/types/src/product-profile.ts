export type ProductProfileStatus = "active" | "archived";

export interface ProductProfile {
  id: string;
  workspace_id: string;
  product_name: string;
  asin?: string | null;
  sku?: string | null;
  marketplace: string;
  currency: string;
  target_acos: string;
  default_budget: string;
  default_bid: string;
  status: ProductProfileStatus;
  created_at: string;
  updated_at: string;
}

