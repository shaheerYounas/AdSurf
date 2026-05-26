import { apiBaseUrl, localAuthHeaders, readApiData } from "@/lib/api/client";

export type CampaignPlan = {
  id: string;
  status: string;
  version: number;
  plan_json: {
    campaigns: Array<{
      campaign_name: string;
      match_type: string;
      keywords: Array<{ search_term: string; relevance_score: number; bid: string }>;
      negative_keywords: Array<{ keyword_text: string; match_type: string; rule: string }>;
    }>;
  };
};

export type BulkExportResponse = {
  export: {
    id: string;
    status: string;
    original_filename: string;
    rows_json: Array<Record<string, string>>;
  };
  download_url: string;
};

export async function createCampaignPlan(workspaceId: string, productId: string, keywordSetId: string): Promise<CampaignPlan> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/campaign-plans`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify({ approved_keyword_set_id: keywordSetId }),
  });
  return readApiData(response, "Campaign plan could not be generated.");
}

export async function approveCampaignPlan(workspaceId: string, planId: string, approvalNote: string): Promise<CampaignPlan> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/campaign-plans/${planId}/approve`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify({ approval_note: approvalNote }),
  });
  return readApiData(response, "Campaign plan could not be approved.");
}

export async function createBulkExport(workspaceId: string, planId: string, approvalNote: string): Promise<BulkExportResponse> {
  const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/campaign-plans/${planId}/exports`, {
    method: "POST",
    headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
    body: JSON.stringify({ approval_note: approvalNote, format: "csv" }),
  });
  return readApiData(response, "Bulk export could not be generated.");
}

export function absoluteApiUrl(path: string) {
  return `${apiBaseUrl}${path}`;
}
