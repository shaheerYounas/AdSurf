"use client";

import { Brain, CheckCircle2, ChevronDown, ChevronUp, Lightbulb, ListChecks, Loader2, RefreshCw, XCircle } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { apiBaseUrl, defaultWorkspaceId, formatApiError, localAuthHeaders, newIdempotencyKey } from "@/lib/api/client";
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

type AiRecommendation = {
  suggested_mapping: {
    search_term: string | null;
    search_volume: string | null;
    competitor_rank_columns: string[];
    confidence: string;
    reasoning: string;
  };
  decision_source: string;
  requires_human_approval: boolean;
  executes_live_amazon_change: boolean;
  validation_messages: Array<{ severity: string; code: string; message: string; column_name?: string }>;
};

const keywordSetConfirmation = "This creates an immutable approved keyword set snapshot for campaign plan generation.";

/** Heuristic confidence colors */
function confidenceColor(level: string): string {
  switch (level) {
    case "high":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-300/10 dark:text-emerald-200";
    case "medium":
      return "bg-amber-100 text-amber-800 dark:bg-amber-300/10 dark:text-amber-200";
    case "low":
      return "bg-red-100 text-red-800 dark:bg-red-300/10 dark:text-red-200";
    default:
      return "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-300";
  }
}

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

  // AI recommendation state
  const [aiRecommendation, setAiRecommendation] = useState<AiRecommendation | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [showAiReasons, setShowAiReasons] = useState(false);

  const canSave = useMemo(() => Boolean(profile && searchTerm && searchVolume && rankColumns.length > 0), [profile, rankColumns, searchTerm, searchVolume]);
  const canScore = mapping?.status === "approved";

  // Find column IDs from original column names (used to apply AI recommendations)
  function columnIdByName(name: string): string | undefined {
    if (!profile) return undefined;
    const col = profile.columns.find(
      (c) => c.original_column_name === name || c.normalized_column_name === name || c.id === name
    );
    return col?.id;
  }

  function columnNameById(id: string): string {
    if (!profile) return id;
    const col = profile.columns.find((c) => c.id === id);
    return col?.original_column_name ?? id;
  }

  /** Apply the AI recommendation to the form fields */
  function applyAiRecommendation() {
    if (!aiRecommendation || !profile) return;
    const mapping = aiRecommendation.suggested_mapping;

    const stId = mapping.search_term ? columnIdByName(mapping.search_term) : "";
    const svId = mapping.search_volume ? columnIdByName(mapping.search_volume) : "";
    const rankIds = mapping.competitor_rank_columns
      .map((name) => columnIdByName(name))
      .filter((id): id is string => Boolean(id));

    setSearchTerm(stId ?? "");
    setSearchVolume(svId ?? "");
    setRankColumns(rankIds);
    setMapping(null);
    setScoringSummary(null);
    setReviews([]);
    setKeywordSet(null);
    setCampaignPlan(null);
    setBulkExport(null);
  }

  async function requestProfile(method: "GET" | "POST") {
    if (!workspaceId.trim()) {
      setMessage("Workspace ID is required.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    setAiRecommendation(null);
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
      setMessage(formatApiError(caught, "Column profile request failed."));
    } finally {
      setIsLoading(false);
    }
  }

  /** Request AI-recommended column mapping */
  async function requestAiRecommendation() {
    if (!profile) {
      setMessage("Generate or load a column profile before requesting AI recommendations.");
      return;
    }
    setMessage(null);
    setAiLoading(true);
    setAiRecommendation(null);
    setMapping(null);
    setScoringSummary(null);
    setReviews([]);
    setKeywordSet(null);
    setCampaignPlan(null);
    setBulkExport(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/column-mappings/recommend`,
        {
          method: "POST",
          headers: localAuthHeaders(workspaceId),
        }
      );
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "AI recommendation request failed.");
      setAiRecommendation(body.data);
    } catch (caught) {
      setMessage(formatApiError(caught, "AI recommendation request failed."));
    } finally {
      setAiLoading(false);
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
      setMessage(formatApiError(caught, "Column mapping save failed."));
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
      setMessage(formatApiError(caught, "Column mapping approval failed."));
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
      setMessage(formatApiError(caught, "Keyword relevance scoring failed."));
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
      setMessage(formatApiError(caught, "Keyword review request failed."));
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
      setMessage(formatApiError(caught, "Keyword override failed."));
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
      setMessage(formatApiError(caught, "Approved keyword set creation failed."));
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
      setMessage(formatApiError(caught, "Campaign plan generation failed."));
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
      setMessage(formatApiError(caught, "Campaign plan approval failed."));
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
      setMessage(formatApiError(caught, "Bulk export failed."));
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
          AI analyzes your column profile and recommends the best mapping. You can accept, adjust, or override the
          suggestion before saving. Deterministic rules validate every mapping.
        </p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Manual column mapping is available here. After approving a valid mapping, you can run deterministic keyword relevance scoring. Then create an approved keyword set before campaign plan generation.
        </p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
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

      {/* AI Recommendation Panel */}
      {profile ? (
        <AiRecommendationPanel
          aiLoading={aiLoading}
          aiRecommendation={aiRecommendation}
          applyAiRecommendation={applyAiRecommendation}
          confidenceColor={confidenceColor}
          columnNameById={columnNameById}
          onRequestRecommendation={requestAiRecommendation}
          showAiReasons={showAiReasons}
          setShowAiReasons={setShowAiReasons}
        />
      ) : null}

      {profile ? (
        <form className="space-y-4 rounded-md border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-950/70" onSubmit={saveMapping}>
          {/* AI-recommended indicator on each select */}
          <div className="flex items-center gap-2 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:bg-blue-300/10 dark:text-blue-200">
            <Lightbulb aria-hidden="true" size={14} />
            {aiRecommendation ? "AI recommendation loaded. Fields show the suggested mapping. Change any before saving." : "Click \"Get AI Recommendation\" above to pre-fill this form automatically."}
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <ColumnSelect
              label="Search term column"
              onChange={setSearchTerm}
              options={profile.columns}
              value={searchTerm}
              aiRecommended={aiRecommendation ? columnIdByName(aiRecommendation.suggested_mapping.search_term ?? "") : undefined}
            />
            <ColumnSelect
              label="Search volume column"
              onChange={setSearchVolume}
              options={profile.columns}
              value={searchVolume}
              aiRecommended={aiRecommendation ? columnIdByName(aiRecommendation.suggested_mapping.search_volume ?? "") : undefined}
            />
            <RankColumnsSelect
              label="Competitor rank columns"
              onChange={setRankColumns}
              options={profile.columns}
              value={rankColumns}
              aiRecommendedIds={
                aiRecommendation
                  ? aiRecommendation.suggested_mapping.competitor_rank_columns
                      .map((name) => columnIdByName(name))
                      .filter((id): id is string => Boolean(id))
                  : undefined
              }
            />
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

/** AI Recommendation Panel — shows the suggestion with reasoning and apply button */
function AiRecommendationPanel({
  aiLoading,
  aiRecommendation,
  applyAiRecommendation,
  confidenceColor,
  columnNameById,
  onRequestRecommendation,
  showAiReasons,
  setShowAiReasons,
}: {
  aiLoading: boolean;
  aiRecommendation: AiRecommendation | null;
  applyAiRecommendation: () => void;
  confidenceColor: (level: string) => string;
  columnNameById: (id: string) => string;
  onRequestRecommendation: () => void;
  showAiReasons: boolean;
  setShowAiReasons: (value: boolean) => void;
}) {
  return (
    <div className="rounded-md border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-300/20 dark:bg-indigo-950/20">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Brain aria-hidden="true" className="text-indigo-600 dark:text-indigo-400" size={18} />
          <span className="text-sm font-semibold text-indigo-800 dark:text-indigo-200">
            AI Column Mapping Recommendation
          </span>
        </div>
        {!aiRecommendation ? (
          <Button
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700"
            disabled={aiLoading}
            onClick={onRequestRecommendation}
            type="button"
          >
            {aiLoading ? <Loader2 aria-hidden="true" className="animate-spin" size={14} /> : <Brain aria-hidden="true" size={14} />}
            {aiLoading ? "Analyzing columns..." : "Get AI Recommendation"}
          </Button>
        ) : null}
      </div>

      {aiRecommendation ? (
        <div className="mt-3 space-y-3">
          {/* Confidence badge and source */}
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${confidenceColor(aiRecommendation.suggested_mapping.confidence)}`}>
              {aiRecommendation.suggested_mapping.confidence === "high" ? (
                <CheckCircle2 size={12} />
              ) : aiRecommendation.suggested_mapping.confidence === "low" ? (
                <XCircle size={12} />
              ) : null}
              {aiRecommendation.suggested_mapping.confidence.toUpperCase()} confidence
            </span>
            <span className="text-slate-500 dark:text-slate-400">
              Source: {aiRecommendation.decision_source === "deterministic" ? "Deterministic rules" : "AI analysis"}
            </span>
          </div>

          {/* Reason — expandable concise 1-4 liner */}
          <div className="rounded-md border border-indigo-200 bg-white p-3 dark:border-indigo-300/20 dark:bg-slate-900/60">
            <button
              className="flex w-full items-center justify-between text-left text-sm font-medium text-indigo-800 dark:text-indigo-200"
              onClick={() => setShowAiReasons(!showAiReasons)}
              type="button"
            >
              <span className="flex items-center gap-1.5">
                <Lightbulb size={14} />
                Why this mapping?
              </span>
              {showAiReasons ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {showAiReasons ? (
              <p className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                {aiRecommendation.suggested_mapping.reasoning || "No reasoning provided — the model selected these columns based on column name patterns, inferred data types, and sample value analysis."}
              </p>
            ) : null}
          </div>

          {/* Validation messages from AI */}
          {aiRecommendation.validation_messages.length > 0 ? (
            <ul className="space-y-1">
              {aiRecommendation.validation_messages.map((msg) => (
                <li
                  key={msg.code + msg.message}
                  className={
                    msg.severity === "error"
                      ? "text-xs text-red-700 dark:text-red-300"
                      : msg.severity === "warning"
                        ? "text-xs text-amber-700 dark:text-amber-300"
                        : "text-xs text-slate-600 dark:text-slate-400"
                  }
                >
                  [{msg.severity.toUpperCase()}] {msg.message}
                </li>
              ))}
            </ul>
          ) : null}

          {/* Apply button */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700"
              onClick={applyAiRecommendation}
              type="button"
            >
              <CheckCircle2 aria-hidden="true" size={14} />
              Apply recommended mapping to form
            </Button>
            <Button
              className="bg-slate-200 text-slate-700 hover:bg-slate-300 dark:bg-white/10 dark:text-white"
              onClick={onRequestRecommendation}
              disabled={aiLoading}
              type="button"
            >
              {aiLoading ? <Loader2 aria-hidden="true" className="animate-spin" size={14} /> : <RefreshCw aria-hidden="true" size={14} />}
              {aiLoading ? "Regenerating..." : "Regenerate"}
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
  aiRecommended,
}: {
  label: string;
  onChange: (value: string) => void;
  options: ColumnProfileColumn[];
  value: string;
  aiRecommended?: string;
}) {
  return (
    <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
      <span className="flex items-center gap-1.5">
        {label}
        {aiRecommended && value === aiRecommended ? (
          <span className="inline-flex items-center gap-0.5 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700 dark:bg-indigo-300/10 dark:text-indigo-300">
            <Brain size={10} /> AI suggested
          </span>
        ) : null}
      </span>
      <select className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => onChange(event.target.value)} value={value}>
        <option value="">Choose a column</option>
        {options.map((column) => (
          <option key={column.id} value={column.id}>
            {column.original_column_name}
            {aiRecommended && column.id === aiRecommended ? " ★ (AI recommended)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

function RankColumnsSelect({
  label,
  onChange,
  options,
  value,
  aiRecommendedIds,
}: {
  label: string;
  onChange: (value: string[]) => void;
  options: ColumnProfileColumn[];
  value: string[];
  aiRecommendedIds?: string[];
}) {
  return (
    <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
      <span className="flex items-center gap-1.5">
        {label}
        {aiRecommendedIds && aiRecommendedIds.length > 0 ? (
          <span className="inline-flex items-center gap-0.5 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700 dark:bg-indigo-300/10 dark:text-indigo-300">
            <Brain size={10} /> AI suggested
          </span>
        ) : null}
      </span>
      <select className="block h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" multiple onChange={(event) => onChange(Array.from(event.target.selectedOptions, (option) => option.value))} value={value}>
        {options.map((column) => (
          <option key={column.id} value={column.id}>
            {column.original_column_name}
            {aiRecommendedIds && aiRecommendedIds.includes(column.id) ? " ★ (AI recommended)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
