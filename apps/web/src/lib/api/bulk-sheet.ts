import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, readApiData } from "@/lib/api/client";

export type BulkCampaign = {
  campaign_id: string;
  name: string;
  status: string;
  daily_budget: number | null;
  targeting_type: string | null;
  start_date: string | null;
  end_date: string | null;
  bidding_strategy: string | null;
};

export type BulkAdGroup = {
  ad_group_id: string;
  campaign_id: string;
  campaign_name: string;
  name: string;
  status: string;
  default_bid: number | null;
};

export type BulkKeyword = {
  keyword_id: string;
  campaign_id: string;
  campaign_name: string;
  ad_group_id: string;
  ad_group_name: string;
  keyword_text: string;
  match_type: string;
  bid: number | null;
  status: string;
};

export type BulkTarget = {
  target_id: string;
  campaign_id: string;
  campaign_name: string;
  ad_group_id: string;
  ad_group_name: string;
  expression: string;
  bid: number | null;
  status: string;
};

export type BulkNegativeKeyword = {
  campaign_id: string;
  campaign_name: string;
  ad_group_id: string;
  ad_group_name: string;
  keyword_text: string;
  match_type: string;
};

export type BulkProductAd = {
  ad_id: string;
  campaign_id: string;
  campaign_name: string;
  ad_group_id: string;
  ad_group_name: string;
  asin: string | null;
  sku: string | null;
  status: string;
};

export type BulkSheetStats = {
  total_campaigns: number;
  active_campaigns: number;
  total_ad_groups: number;
  total_keywords: number;
  total_targets: number;
  total_product_ads: number;
  total_negative_keywords: number;
};

export type BulkSheetSnapshot = {
  filename: string;
  date_range_start: string | null;
  date_range_end: string | null;
  account_id: string | null;
  stats: BulkSheetStats;
  campaigns: BulkCampaign[];
  ad_groups: BulkAdGroup[];
  keywords: BulkKeyword[];
  targets: BulkTarget[];
  negative_keywords: BulkNegativeKeyword[];
  product_ads: BulkProductAd[];
  warnings: string[];
};

export async function parseBulkSheet(
  workspaceId: string,
  file: File,
): Promise<BulkSheetSnapshot> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${apiBaseUrl}/v1/workspaces/${workspaceId}/bulk-sheet/parse`,
    {
      method: "POST",
      headers: localAuthHeaders(workspaceId),
      body: formData,
    },
  );

  return readApiData<BulkSheetSnapshot>(res, "Failed to parse bulk sheet.");
}
