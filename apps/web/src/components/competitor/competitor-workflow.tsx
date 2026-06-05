"use client";

import { Activity, Bot, CheckCircle2, FileSearch, Loader2, Play, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import {
  generateCampaignsFromVerified,
  getCompetitorCleanedRows,
  getCompetitorUpload,
  scoreCompetitorUpload,
  simulate14DayMonitoring,
  uploadCompetitorCsv,
  verifyCompetitorKeywordsAgentic,
  type CampaignGenerationResponse,
  type CompetitorCleanedRow,
  type CompetitorUploadRecord,
  type CompetitorVerificationEvidenceRow,
  type MonitoringDayResult,
} from "@/lib/api/competitor";
import { getProductProfile } from "@/lib/api/products";

type CompetitorWorkflowProps = {
  productId: string;
};

type WorkflowPhase = "full" | "phase1" | "phase2" | "phase3";

export function CompetitorWorkflow({ productId }: CompetitorWorkflowProps) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [phase, setPhase] = useState<WorkflowPhase>("full");
  const [productName, setProductName] = useState("Product");
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<CompetitorUploadRecord | null>(null);
  const [existingUploadId, setExistingUploadId] = useState("");
  const [rows, setRows] = useState<CompetitorCleanedRow[]>([]);
  const [competitorsText, setCompetitorsText] = useState("");
  const [marketplace, setMarketplace] = useState("US");
  const [maxKeywords, setMaxKeywords] = useState(25);
  const [agentEvidenceRows, setAgentEvidenceRows] = useState<CompetitorVerificationEvidenceRow[]>([]);
  const [campaignPlan, setCampaignPlan] = useState<CampaignGenerationResponse | null>(null);
  const [monitoringCampaignName, setMonitoringCampaignName] = useState("");
  const [monitoringDays, setMonitoringDays] = useState<MonitoringDayResult[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);

  useEffect(() => {
    loadProduct();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rowCounts = useMemo(() => {
    return rows.reduce(
      (counts, row) => {
        if (row.scoring_status === "approved") counts.approved += 1;
        if (row.verification_status === "verified") counts.verified += 1;
        if (row.verification_status === "unverified") counts.unverified += 1;
        return counts;
      },
      { approved: 0, verified: 0, unverified: 0 },
    );
  }, [rows]);
  const approvedRows = useMemo(() => rows.filter((row) => row.scoring_status === "approved" && row.search_term), [rows]);
  const showPhase1 = phase === "full" || phase === "phase1";
  const showPhase2 = phase === "full" || phase === "phase2";
  const showPhase3 = phase === "full" || phase === "phase3";

  async function loadProduct() {
    setIsLoading(true);
    setMessage(null);
    try {
      const product = await getProductProfile(productId, workspaceId);
      setProductName(product.product_name);
    } catch (caught) {
      setMessage(formatApiError(caught, "Product could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshRows(uploadId = upload?.id) {
    if (!uploadId) return;
    const response = await getCompetitorCleanedRows(uploadId, 1, 50, workspaceId);
    setRows(response.rows);
  }

  async function handleLoadExistingUpload() {
    if (!existingUploadId.trim()) {
      setMessage("Enter an existing competitor upload ID.");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      const loadedUpload = await getCompetitorUpload(existingUploadId.trim(), workspaceId);
      setUpload(loadedUpload);
      await refreshRows(loadedUpload.id);
      setCampaignPlan(null);
      setMessage("Loaded existing competitor upload. You can continue the selected phase.");
    } catch (caught) {
      setMessage(formatApiError(caught, "Existing upload could not be loaded."));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleUpload() {
    if (!file) {
      setMessage("Choose a competitor CSV first.");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      const response = await uploadCompetitorCsv(file, workspaceId);
      setUpload(response.upload);
      setExistingUploadId(response.upload.id);
      setRows(response.cleaned_rows);
      setCampaignPlan(null);
      setMessage(`Uploaded and cleaned ${response.total_rows} rows.`);
    } catch (caught) {
      setMessage(formatApiError(caught, "Competitor upload failed."));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleScore() {
    if (!upload) {
      setMessage("Upload a competitor file first.");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      const response = await scoreCompetitorUpload(upload.id, workspaceId);
      setRows(response.preview_rows);
      setMessage(`Scored ${response.scored_rows} rows: ${response.approved_count} approved, ${response.rejected_count} rejected.`);
    } catch (caught) {
      setMessage(formatApiError(caught, "Scoring failed."));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleAgenticVerify() {
    if (!upload) {
      setMessage("Upload and score a competitor file first.");
      return;
    }
    const competitors = competitorsText.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
    if (!competitors.length) {
      setMessage("Enter at least one competitor name or ASIN.");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      const response = await verifyCompetitorKeywordsAgentic(upload.id, {
        competitors,
        required_match_count: 3,
        max_keywords: maxKeywords,
        marketplace,
        headless: true,
      }, workspaceId);
      setRows(response.preview_rows);
      setAgentEvidenceRows(response.evidence_rows);
      setMessage(`Verification agent checked ${response.evidence_rows.length} Amazon searches and verified ${response.verified_count} rows. ${response.unverified_count} rows remain unverified.`);
    } catch (caught) {
      setMessage(formatApiError(caught, "Agentic browser verification failed."));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleGenerateCampaigns() {
    if (!upload) {
      setMessage("Verify competitor keywords before campaign generation.");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      const response = await generateCampaignsFromVerified(upload.id, { product_id: productId, product_name: productName, batch_size: 7, daily_budget: 10, default_bid: 1 }, workspaceId);
      setCampaignPlan(response);
      setMonitoringCampaignName(response.hero_campaign_name);
      setMessage(`Generated ${response.campaign_count} approval-controlled campaigns.`);
    } catch (caught) {
      setMessage(formatApiError(caught, "Campaign generation failed."));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSimulateMonitoring() {
    const campaignName = monitoringCampaignName.trim() || campaignPlan?.hero_campaign_name;
    if (!campaignName) {
      setMessage("Enter a campaign name or generate campaigns first.");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      const response = await simulate14DayMonitoring({ product_id: productId, campaign_name: campaignName, daily_budget: 10, starting_bid: 1 }, workspaceId);
      setMonitoringDays(response);
      setMessage(`Simulated ${response.length} monitoring days. Recommendations remain approval-gated.`);
    } catch (caught) {
      setMessage(formatApiError(caught, "14-day monitoring simulation failed."));
    } finally {
      setIsWorking(false);
    }
  }

  if (isLoading) return <LoadingSpinner message="Loading competitor workflow" subtext="Fetching product defaults" />;

  return (
    <div className="space-y-5">
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Workflow phase">
          <PhaseButton current={phase} value="full" label="Full flow" onChange={setPhase} />
          <PhaseButton current={phase} value="phase1" label="Phase 1" onChange={setPhase} />
          <PhaseButton current={phase} value="phase2" label="Phase 2" onChange={setPhase} />
          <PhaseButton current={phase} value="phase3" label="Phase 3" onChange={setPhase} />
        </div>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {phase === "phase1" ? "Phase 1 cleans, scores, and verifies competitor keywords with the Amazon browser verification agent." : null}
          {phase === "phase2" ? "Phase 2 prepares campaign rows only from approved and verified keywords." : null}
          {phase === "phase3" ? "Phase 3 runs the deterministic 14-day monitoring loop for a campaign name." : null}
          {phase === "full" ? "Full flow runs competitor research, campaign preparation, and 14-day monitoring preparation behind approval boundaries." : null}
        </p>
      </div>

      {showPhase1 ? (
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Competitor research CSV
            <input
              accept=".csv"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-full file:border-0 file:bg-slate-950 file:px-3 file:py-1 file:text-white dark:border-white/10 dark:bg-white/5 dark:text-white dark:file:bg-white dark:file:text-slate-950"
              id="competitor-research-file"
              name="competitor_research_file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              type="file"
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Workspace ID
            <input id="competitor-workspace-id" name="competitor_workspace_id" className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button className="inline-flex items-center gap-2" disabled={isWorking} onClick={handleUpload} type="button">
            {isWorking ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <UploadCloud aria-hidden="true" size={16} />}
            Upload
          </Button>
          <Button className="inline-flex items-center gap-2" disabled={!upload || isWorking} onClick={handleScore} type="button" variant="secondary">
            <FileSearch aria-hidden="true" size={16} />
            Score
          </Button>
        </div>
      </div>
      ) : null}

      {showPhase2 ? (
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Existing upload ID for phase 2
            <input id="existing-competitor-upload-id" name="existing_competitor_upload_id" className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setExistingUploadId(event.target.value)} placeholder="Paste competitor upload ID" value={existingUploadId} />
          </label>
          <Button className="mt-7 inline-flex items-center gap-2" disabled={isWorking} onClick={handleLoadExistingUpload} type="button" variant="secondary">
            <FileSearch aria-hidden="true" size={16} />
            Load upload
          </Button>
        </div>
      </div>
      ) : null}

      {showPhase1 ? (
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="grid gap-4 lg:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Original competitors
            <textarea id="competitor-reference-list" name="competitor_reference_list" className="min-h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setCompetitorsText(event.target.value)} placeholder="Competitor A, Competitor B, Competitor C" value={competitorsText} />
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Marketplace
            <select id="competitor-marketplace" name="competitor_marketplace" className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setMarketplace(event.target.value)} value={marketplace}>
              <option value="US">Amazon US</option>
              <option value="CA">Amazon CA</option>
              <option value="UK">Amazon UK</option>
              <option value="DE">Amazon DE</option>
              <option value="FR">Amazon FR</option>
              <option value="IT">Amazon IT</option>
              <option value="ES">Amazon ES</option>
            </select>
          </label>
        </div>
        <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-950 dark:text-white">Agentic Amazon browser verification</p>
              <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                The agent opens Amazon search pages, reads the visible top 15 results, stores the extracted evidence, and rules verify competitor matches. It does not log in, bypass challenges, scrape with stealth, or execute Amazon Ads changes.
              </p>
            </div>
            <label className="space-y-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Max keywords
              <input id="competitor-max-keywords" name="competitor_max_keywords" className="block w-24 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" max={100} min={1} onChange={(event) => setMaxKeywords(Number(event.target.value))} type="number" value={maxKeywords} />
            </label>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Metric label="Approved to search" value={String(Math.min(approvedRows.length, maxKeywords))} />
            <Metric label="Top results per term" value="15" />
            <Metric label="Required matches" value="3" />
          </div>
          {agentEvidenceRows.length ? (
            <div className="mt-4 rounded-md border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-950/70">
              <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Evidence extracted</p>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{agentEvidenceRows.length} search pages checked by the browser agent.</p>
            </div>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button className="inline-flex items-center gap-2" disabled={!upload || isWorking} onClick={handleAgenticVerify} type="button" variant="accent">
            {isWorking ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <Bot aria-hidden="true" size={16} />}
            Run verification agent
          </Button>
        </div>
      </div>
      ) : null}

      {showPhase2 ? (
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-950 dark:text-white">Phase 2 campaign preparation</p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Uses only rows with approved scoring and verified browser-agent evidence.</p>
          </div>
          <Button className="inline-flex items-center gap-2" disabled={!upload || rowCounts.verified === 0 || isWorking} onClick={handleGenerateCampaigns} type="button" variant="success">
            <Play aria-hidden="true" size={16} />
            Generate campaigns
          </Button>
        </div>
      </div>
      ) : null}

      {message ? <p className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-800 dark:bg-white/10 dark:text-slate-100">{message}</p> : null}

      <div className="grid gap-3 sm:grid-cols-4">
        <Metric label="Cleaned rows" value={String(upload?.row_count ?? rows.length)} />
        <Metric label="Approved" value={String(rowCounts.approved)} />
        <Metric label="Verified" value={String(rowCounts.verified)} />
        <Metric label="Unverified" value={String(rowCounts.unverified)} />
      </div>

      <div className="rounded-md border border-slate-200 bg-white dark:border-white/10 dark:bg-slate-950/70">
        <div className="border-b border-slate-200 px-5 py-3 text-sm font-medium text-slate-900 dark:border-white/10 dark:text-white">Verification preview</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-5 py-3">Search term</th>
                <th className="px-5 py-3">Score</th>
                <th className="px-5 py-3">Scoring</th>
                <th className="px-5 py-3">Verification</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-white/10">
              {rows.slice(0, 12).map((row) => (
                <tr key={row.id}>
                  <td className="px-5 py-3 font-medium text-slate-950 dark:text-white">{row.search_term ?? "-"}</td>
                  <td className="px-5 py-3 text-slate-700 dark:text-slate-200">{row.relevance_score ?? "-"}</td>
                  <td className="px-5 py-3 text-slate-700 dark:text-slate-200">{row.scoring_status ?? "-"}</td>
                  <td className="px-5 py-3 text-slate-700 dark:text-slate-200">{row.verification_status ?? "-"}</td>
                </tr>
              ))}
              {!rows.length ? (
                <tr>
                  <td className="px-5 py-8 text-slate-500 dark:text-slate-400" colSpan={4}>No cleaned rows yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {campaignPlan ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-300/25 dark:bg-emerald-300/10">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900 dark:text-emerald-100">
            <CheckCircle2 aria-hidden="true" size={18} />
            {campaignPlan.hero_campaign_name}
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <tbody>
                {campaignPlan.bulk_export_preview.slice(0, 8).map((row, index) => (
                  <tr className="border-t border-emerald-200/70 dark:border-emerald-300/20" key={`${row["Record Type"]}-${index}`}>
                    <td className="px-2 py-2">{row["Record Type"]}</td>
                    <td className="px-2 py-2">{row["Campaign Name"]}</td>
                    <td className="px-2 py-2">{row["Keyword Text"]}</td>
                    <td className="px-2 py-2">{row["Match Type"]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {showPhase3 ? (
        <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
            <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
              Campaign name for phase 3
              <input id="monitoring-campaign-name" name="monitoring_campaign_name" className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setMonitoringCampaignName(event.target.value)} placeholder="Product / SP / Manual / Exact / keyword / Jun 2" value={monitoringCampaignName} />
            </label>
            <Button className="mt-7 inline-flex items-center gap-2" disabled={isWorking} onClick={handleSimulateMonitoring} type="button" variant="secondary">
              <Activity aria-hidden="true" size={16} />
              Simulate 14 days
            </Button>
          </div>
          {monitoringDays.length ? (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Day</th>
                    <th className="px-3 py-2">Spend</th>
                    <th className="px-3 py-2">Action</th>
                    <th className="px-3 py-2">Suggested bid</th>
                    <th className="px-3 py-2">Locked</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-white/10">
                  {monitoringDays.map((day) => (
                    <tr key={day.day}>
                      <td className="px-3 py-2">{day.day}</td>
                      <td className="px-3 py-2">${day.spend}</td>
                      <td className="px-3 py-2">{day.action}</td>
                      <td className="px-3 py-2">${day.suggested_bid}</td>
                      <td className="px-3 py-2">{day.locked ? "yes" : "no"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PhaseButton({ current, value, label, onChange }: { current: WorkflowPhase; value: WorkflowPhase; label: string; onChange: (value: WorkflowPhase) => void }) {
  return (
    <button
      aria-selected={current === value}
      className={`rounded-md border px-3 py-2 text-sm font-semibold transition ${current === value ? "border-slate-950 bg-slate-950 text-white dark:border-white dark:bg-white dark:text-slate-950" : "border-slate-200 bg-white text-slate-700 hover:border-slate-400 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"}`}
      onClick={() => onChange(value)}
      role="tab"
      type="button"
    >
      {label}
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-950/70">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">{value}</p>
    </div>
  );
}
