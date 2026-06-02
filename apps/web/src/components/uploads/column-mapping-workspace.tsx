"use client";

import { CheckCircle2, ListChecks, Loader2, RefreshCw } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, newIdempotencyKey } from "@/lib/api/client";
import {
  approveCampaignPlan,
  createBulkExport,
  createCampaignPlan,
  type BulkExportResponse,
  type CampaignPlan,
} from "@/lib/api/campaigns";

type ColumnMappingWorkspaceProps = {
  productId: string;
  uploadId: string;
};

type ColumnProfileColumn = {
  id: string;
  original_column_name: string;
  normalized_column_name: string;
  inferred_data_type: string;
  non_null_count: number;
  sample_values_json: unknown[];
};

type ColumnProfileResponse = {
  profile: { id: string };
  columns: ColumnProfileColumn[];
};

type ColumnMapping = {
  id: string;
  status: string;
  mapping_version: number;
  validation_errors_json: Array<{ severity: string; code: string; message: string; column_name?: string }>;
};

type ScoringSummary = {
  scoring_run_id: string;
  status: string;
  total_rows: number;
  approved_count: number;
  rejected_count: number;
  error_count: number;
};

type KeywordCandidateReview = {
  id: string;
  search_term: string | null;
  search_volume: string | number | null;
  relevance_score: number | null;
  original_scoring_status: string;
  effective_status: string;
  rejection_reason: string | null;
  override: { id: string; override_action: string; reason: string; new_status: string } | null;
};

type ApprovedKeywordSet = {
  id: string;
  name: string;
  status: string;
  keyword_count: number;
};

const keywordSetConfirmation = "This creates an immutable approved keyword set snapshot for campaign plan generation.";

export function ColumnMappingWorkspace({ productId, uploadId }: ColumnMappingWorkspaceProps) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [profile, setProfile] = useState<ColumnProfileResponse | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchVolume, setSearchVolume] = useState("");
  const [rankColumns, setRankColumns] = useState<string[]>([]);
  const [scoringSummary, setScoringSummary] = useState<ScoringSummary | null>(null);
  const [reviews, setReviews] = useState<KeywordCandidateReview[]>([]);
  const [effectiveStatusFilter, setEffectiveStatusFilter] = useState("");
  const [hasOverrideFilter, setHasOverrideFilter] = useState("");
  const [minScore, setMinScore] = useState("");
  const [maxScore, setMaxScore] = useState("");
  const [overrideTarget, setOverrideTarget] = useState<KeywordCandidateReview | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [keywordSetName, setKeywordSetName] = useState("");
  const [keywordSet, setKeywordSet] = useState<ApprovedKeywordSet | null>(null);
  const [campaignPlan, setCampaignPlan] = useState<CampaignPlan | null>(null);
  const [planApprovalNote, setPlanApprovalNote] = useState("");
  const [exportApprovalNote, setExportApprovalNote] = useState("");
  const [bulkExport, setBulkExport] = useState<BulkExportResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const canSave = useMemo(() => Boolean(profile && searchTerm && searchVolume && rankColumns.length > 0), [profile, rankColumns, searchTerm, searchVolume]);
  const canScore = mapping?.status === "approved";

  async function requestProfile(method: "GET" | "POST") {
    if (!workspaceId.trim()) {
      setMessage("Workspace ID is required.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/column-profile`, {
        method,
        headers: localAuthHeaders(workspaceId),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Column profile request failed.");
      setProfile(body.data);
      setMapping(null);
      setScoringSummary(null);
      setReviews([]);
      setKeywordSet(null);
      setCampaignPlan(null);
      setBulkExport(null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Column profile request failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function saveMapping(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile) {
      setMessage("Generate or load a column profile before saving a mapping.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/column-mappings`, {
        method: "POST",
        headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
        body: JSON.stringify({
          column_profile_id: profile.profile.id,
          mapping_json: {
            search_term: searchTerm,
            search_volume: searchVolume,
            competitor_rank_columns: rankColumns,
          },
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Column mapping save failed.");
      setMapping(body.data);
      setScoringSummary(null);
      setReviews([]);
      setKeywordSet(null);
      setCampaignPlan(null);
      setBulkExport(null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Column mapping save failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function approveMapping() {
    if (!mapping) {
      setMessage("Save a valid mapping before approving it.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/column-mappings/${mapping.id}/approve`, {
        method: "POST",
        headers: localAuthHeaders(workspaceId),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Column mapping approval failed.");
      setMapping(body.data);
      setScoringSummary(null);
      setReviews([]);
      setKeywordSet(null);
      setCampaignPlan(null);
      setBulkExport(null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Column mapping approval failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function runScoring() {
    if (!mapping || !canScore) {
      setMessage("Approve a valid mapping before running keyword relevance scoring.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/column-mappings/${mapping.id}/score`, {
        method: "POST",
        headers: { ...localAuthHeaders(workspaceId), "Idempotency-Key": newIdempotencyKey() },
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Keyword relevance scoring failed.");
      setScoringSummary(body.data);
      await loadReviews(body.data.scoring_run_id);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Keyword relevance scoring failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadReviews(scoringRunId = scoringSummary?.scoring_run_id) {
    if (!scoringRunId) {
      setMessage("Run scoring before loading keyword reviews.");
      return;
    }
    setMessage(null);
    try {
      const params = new URLSearchParams({ page: "1", page_size: "50" });
      if (effectiveStatusFilter) params.set("effective_status", effectiveStatusFilter);
      if (hasOverrideFilter) params.set("has_override", hasOverrideFilter);
      if (minScore) params.set("min_relevance_score", minScore);
      if (maxScore) params.set("max_relevance_score", maxScore);
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/scoring-runs/${scoringRunId}/candidates/review?${params.toString()}`, {
        headers: localAuthHeaders(workspaceId),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Keyword review request failed.");
      setReviews(body.data);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Keyword review request failed.");
    }
  }

  async function saveOverride() {
    if (!overrideTarget) {
      setMessage("Choose a keyword candidate before saving an override.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/keyword-candidates/${overrideTarget.id}/override`, {
        method: "POST",
        headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
        body: JSON.stringify({
          override_action: overrideTarget.effective_status === "approved" ? "reject" : "approve",
          reason: overrideReason,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Keyword override failed.");
      setOverrideTarget(null);
      setOverrideReason("");
      await loadReviews();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Keyword override failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function createKeywordSet() {
    if (!scoringSummary) {
      setMessage("Run scoring before creating an approved keyword set.");
      return;
    }
    const confirmed = typeof globalThis.confirm === "function" ? globalThis.confirm(keywordSetConfirmation) : true;
    if (!confirmed) return;
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/scoring-runs/${scoringSummary.scoring_run_id}/approved-keyword-sets`, {
        method: "POST",
        headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
        body: JSON.stringify({ name: keywordSetName }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Approved keyword set creation failed.");
      setKeywordSet(body.data);
      setCampaignPlan(null);
      setBulkExport(null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Approved keyword set creation failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function generateCampaignPlan() {
    if (!keywordSet) {
      setMessage("Create an approved keyword set before generating a campaign plan.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const plan = await createCampaignPlan(workspaceId, productId, keywordSet.id);
      setCampaignPlan(plan);
      setBulkExport(null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Campaign plan generation failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function approvePlan() {
    if (!campaignPlan) {
      setMessage("Generate a campaign plan before approving it.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const plan = await approveCampaignPlan(workspaceId, campaignPlan.id, planApprovalNote);
      setCampaignPlan(plan);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Campaign plan approval failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function approveAndExport() {
    if (!campaignPlan) {
      setMessage("Approve a campaign plan before generating a bulk export.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const exportResponse = await createBulkExport(workspaceId, campaignPlan.id, exportApprovalNote);
      setBulkExport(exportResponse);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Bulk export failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function downloadExport() {
    if (!bulkExport) {
      setMessage("Generate a bulk export before downloading it.");
      return;
    }
    const response = await fetch(`${apiBaseUrl}${bulkExport.download_url}`, {
      headers: localAuthHeaders(workspaceId),
    });
    if (!response.ok) {
      setMessage("Bulk export download failed.");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = bulkExport.export.original_filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-950/70">
        <p className="text-sm font-medium text-slate-900 dark:text-white">
          Manual column mapping is available here. After approving a valid mapping, you can run deterministic keyword relevance scoring.
          Then create an approved keyword set, generate a campaign plan, approve it, and download a bulk export CSV.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_auto]">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Workspace ID
            <input className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setWorkspaceId(event.target.value)} placeholder="Workspace UUID" value={workspaceId} />
          </label>
          <Button className="mt-7 inline-flex items-center gap-2" disabled={isLoading} onClick={() => requestProfile("POST")} type="button">
            <RefreshCw aria-hidden="true" size={16} />
            Generate profile
          </Button>
          <Button className="mt-7 inline-flex items-center gap-2 bg-slate-700" disabled={isLoading} onClick={() => requestProfile("GET")} type="button">
            <ListChecks aria-hidden="true" size={16} />
            Load profile
          </Button>
        </div>
        <p className="mt-2 font-mono text-xs text-slate-500 dark:text-slate-400">Product {productId} / Upload {uploadId}</p>
      </div>

      {message ? <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-300/10 dark:text-red-100">{message}</p> : null}

      {isLoading ? <LoadingSpinner message="Processing workflow step" subtext="This may take a moment while workers process your data" /> : null}

      {profile ? <ColumnProfileTable profile={profile} /> : null}

      {profile ? (
        <form className="space-y-4 rounded-md border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-950/70" onSubmit={saveMapping}>
          <div className="grid gap-4 md:grid-cols-3">
            <ColumnSelect label="Search term column" onChange={setSearchTerm} options={profile.columns} value={searchTerm} />
            <ColumnSelect label="Search volume column" onChange={setSearchVolume} options={profile.columns} value={searchVolume} />
            <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
              Competitor rank columns
              <select className="block h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" multiple onChange={(event) => setRankColumns(Array.from(event.target.selectedOptions, (option) => option.value))} value={rankColumns}>
                {profile.columns.map((column) => (
                  <option key={column.id} value={column.id}>
                    {column.original_column_name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button disabled={!canSave || isLoading} type="submit">
              {isLoading ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : null}
              {isLoading ? "Saving..." : "Save manual mapping"}
            </Button>
            <Button className="inline-flex items-center gap-2 bg-emerald-700 disabled:bg-slate-300" disabled={!mapping || mapping.status !== "valid" || isLoading} onClick={approveMapping} type="button">
              {isLoading ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <CheckCircle2 aria-hidden="true" size={16} />}
              {isLoading ? "Approving..." : "Approve valid mapping"}
            </Button>
          </div>
        </form>
      ) : null}

      {mapping ? <MappingStatus mapping={mapping} /> : null}

      {canScore ? (
        <div className="space-y-4 rounded-md border border-slate-200 bg-white p-4 text-sm dark:border-white/10 dark:bg-slate-950/70">
          <p className="font-medium text-slate-900 dark:text-white">This calculates deterministic relevance scores from the approved mapping before campaign planning.</p>
          <div className="flex flex-wrap items-end gap-3">
            <Button disabled={isLoading} onClick={runScoring} type="button">
              Run keyword relevance scoring
            </Button>
            <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
              Effective status
              <select className="block rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setEffectiveStatusFilter(event.target.value)} value={effectiveStatusFilter}>
                <option value="">All</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="error">Error</option>
              </select>
            </label>
            <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
              Has override
              <select className="block rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setHasOverrideFilter(event.target.value)} value={hasOverrideFilter}>
                <option value="">All</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </label>
            <ScoreInput label="Min score" onChange={setMinScore} value={minScore} />
            <ScoreInput label="Max score" onChange={setMaxScore} value={maxScore} />
            <Button className="bg-slate-700" disabled={!scoringSummary || isLoading} onClick={() => loadReviews()} type="button">
              Apply filters
            </Button>
          </div>
          {scoringSummary ? <ScoringSummaryPanel scoringSummary={scoringSummary} /> : null}
          {reviews.length ? <ReviewTable onOverride={setOverrideTarget} reviews={reviews} /> : null}
          {scoringSummary ? (
            <div className="space-y-3 border-t border-slate-200 pt-4 dark:border-white/10">
              <p className="font-medium text-slate-900 dark:text-white">{keywordSetConfirmation}</p>
              <div className="flex flex-wrap items-end gap-3">
                <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                  Keyword set name
                  <input className="block rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setKeywordSetName(event.target.value)} value={keywordSetName} />
                </label>
                <Button disabled={!keywordSetName.trim() || isLoading} onClick={createKeywordSet} type="button">
                  Create approved keyword set
                </Button>
              </div>
              {keywordSet ? (
                <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-300/10 dark:text-emerald-100">
                  Approved keyword set {keywordSet.name} is {keywordSet.status} with {keywordSet.keyword_count} items.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {keywordSet ? (
        <div className="space-y-4 rounded-md border border-slate-200 bg-white p-4 text-sm dark:border-white/10 dark:bg-slate-950/70">
          <div>
            <p className="font-medium text-slate-900 dark:text-white">Campaign plan and bulk export</p>
            <p className="mt-1 text-slate-600 dark:text-slate-300">Generated plans use locked approved keyword snapshots. Exports require approved campaign plans and an explicit approval note.</p>
          </div>
          <Button disabled={isLoading} onClick={generateCampaignPlan} type="button">
            Generate campaign plan
          </Button>
          {campaignPlan ? (
            <div className="space-y-4 border-t border-slate-200 pt-4 dark:border-white/10">
              <p className="font-medium text-slate-900 dark:text-white">
                Campaign plan v{campaignPlan.version}: {campaignPlan.status}
              </p>
              <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-white/10">
                <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-white/10">
                  <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500 dark:bg-white/5 dark:text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Campaign</th>
                      <th className="px-3 py-2">Match</th>
                      <th className="px-3 py-2">Keywords</th>
                      <th className="px-3 py-2">Negatives</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/10">
                    {campaignPlan.plan_json.campaigns.map((campaign) => (
                      <tr key={campaign.campaign_name}>
                        <td className="px-3 py-2 font-medium text-slate-900 dark:text-white">{campaign.campaign_name}</td>
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{campaign.match_type}</td>
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{campaign.keywords.map((keyword) => keyword.search_term).join(", ")}</td>
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{campaign.negative_keywords.length}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {campaignPlan.status !== "approved" ? (
                <div className="flex flex-wrap items-end gap-3">
                  <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Plan approval note
                    <input className="block min-w-72 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setPlanApprovalNote(event.target.value)} value={planApprovalNote} />
                  </label>
                  <Button disabled={!planApprovalNote.trim() || isLoading} onClick={approvePlan} type="button">
                    Approve campaign plan
                  </Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-end gap-3">
                  <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                    Export approval note
                    <input className="block min-w-72 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setExportApprovalNote(event.target.value)} value={exportApprovalNote} />
                  </label>
                  <Button disabled={!exportApprovalNote.trim() || isLoading} onClick={approveAndExport} type="button">
                    Approve and generate bulk sheet
                  </Button>
                </div>
              )}
              {bulkExport ? (
                <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-300/10 dark:text-emerald-100">
                  Bulk export {bulkExport.export.original_filename} is approved with {bulkExport.export.rows_json.length} rows.{" "}
                  <button className="font-medium underline" onClick={downloadExport} type="button">
                    Download CSV
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {overrideTarget ? (
        <div className="rounded-md border border-slate-300 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
          <p className="font-medium text-slate-900 dark:text-white">Override reason</p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{overrideTarget.effective_status === "approved" ? "Reject approved candidate" : "Approve rejected candidate"}: {overrideTarget.search_term}</p>
          <textarea className="mt-3 block h-24 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setOverrideReason(event.target.value)} value={overrideReason} />
          <div className="mt-3 flex gap-2">
            <Button disabled={!overrideReason.trim() || isLoading} onClick={saveOverride} type="button">
              Save override
            </Button>
            <Button className="bg-slate-700" onClick={() => setOverrideTarget(null)} type="button">
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ColumnProfileTable({ profile }: { profile: ColumnProfileResponse }) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200 bg-white dark:border-white/10 dark:bg-slate-950/70">
      <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-white/10">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500 dark:bg-white/5 dark:text-slate-400">
          <tr>
            <th className="px-3 py-2">Original column name</th>
            <th className="px-3 py-2">Normalized column name</th>
            <th className="px-3 py-2">Inferred type</th>
            <th className="px-3 py-2">Non-null count</th>
            <th className="px-3 py-2">Sample values</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-white/10">
          {profile.columns.map((column) => (
            <tr key={column.id}>
              <td className="px-3 py-2 font-medium text-slate-900 dark:text-white">{column.original_column_name}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{column.normalized_column_name}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{column.inferred_data_type}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{column.non_null_count}</td>
              <td className="max-w-md px-3 py-2 text-slate-600 dark:text-slate-300">{column.sample_values_json.slice(0, 5).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MappingStatus({ mapping }: { mapping: ColumnMapping }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 text-sm dark:border-white/10 dark:bg-slate-950/70">
      <p className="font-medium text-slate-900 dark:text-white">
        Mapping v{mapping.mapping_version}: {mapping.status}
      </p>
      {mapping.validation_errors_json.length ? (
        <ul className="mt-3 space-y-2">
          {mapping.validation_errors_json.map((item) => (
            <li className={item.severity === "error" ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300"} key={item.code + item.message}>
              {item.severity}: {item.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ScoringSummaryPanel({ scoringSummary }: { scoringSummary: ScoringSummary }) {
  return (
    <div className="grid gap-3 sm:grid-cols-4">
      <SummaryItem label="Total rows" value={scoringSummary.total_rows} />
      <SummaryItem label="Approved candidates" value={scoringSummary.approved_count} />
      <SummaryItem label="Rejected candidates" value={scoringSummary.rejected_count} />
      <SummaryItem label="Errors" value={scoringSummary.error_count} />
    </div>
  );
}

function ReviewTable({ onOverride, reviews }: { onOverride: (review: KeywordCandidateReview) => void; reviews: KeywordCandidateReview[] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-white/10">
      <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-white/10">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500 dark:bg-white/5 dark:text-slate-400">
          <tr>
            <th className="px-3 py-2">Search term</th>
            <th className="px-3 py-2">Search volume</th>
            <th className="px-3 py-2">Relevance score</th>
            <th className="px-3 py-2">Original status</th>
            <th className="px-3 py-2">Effective status</th>
            <th className="px-3 py-2">Rejection reason</th>
            <th className="px-3 py-2">Override status</th>
            <th className="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-white/10">
          {reviews.map((review) => (
            <tr key={review.id}>
              <td className="px-3 py-2 font-medium text-slate-900 dark:text-white">{review.search_term ?? "-"}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{review.search_volume ?? "-"}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{review.relevance_score ?? "-"}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{review.original_scoring_status}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{review.effective_status}</td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{review.rejection_reason ?? "-"}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{review.override ? review.override.new_status : "none"}</td>
              <td className="px-3 py-2">
                {review.effective_status === "approved" || review.effective_status === "rejected" ? (
                  <Button className="bg-slate-700" onClick={() => onOverride(review)} type="button">
                    {review.effective_status === "approved" ? "Reject" : "Approve"}
                  </Button>
                ) : (
                  <span className="text-slate-400 dark:text-slate-500">Unavailable</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-white/10 dark:bg-white/5">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{value}</p>
    </div>
  );
}

function ScoreInput({ label, onChange, value }: { label: string; onChange: (value: string) => void; value: string }) {
  return (
    <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
      {label}
      <input className="block w-24 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" max="10" min="0" onChange={(event) => onChange(event.target.value)} type="number" value={value} />
    </label>
  );
}

function ColumnSelect({
  label,
  onChange,
  options,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  options: ColumnProfileColumn[];
  value: string;
}) {
  return (
    <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
      {label}
      <select className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => onChange(event.target.value)} value={value}>
        <option value="">Choose a column</option>
        {options.map((column) => (
          <option key={column.id} value={column.id}>
            {column.original_column_name}
          </option>
        ))}
      </select>
    </label>
  );
}
