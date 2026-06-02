"use client";

import { CheckCircle2, FileSearch, Loader2, Play, ShieldCheck, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId } from "@/lib/api/client";
import {
  generateCampaignsFromVerified,
  getCompetitorCleanedRows,
  scoreCompetitorUpload,
  uploadCompetitorCsv,
  verifyCompetitorKeywords,
  type CampaignGenerationResponse,
  type CompetitorCleanedRow,
  type CompetitorUploadRecord,
  type CompetitorVerificationEvidenceRow,
} from "@/lib/api/competitor";
import { getProductProfile } from "@/lib/api/products";

type CompetitorWorkflowProps = {
  productId: string;
};

const sampleEvidence = `[
  {
    "search_term": "coffee beans",
    "results": [
      { "position": 1, "title": "Competitor A beans", "asin": "B0AAA", "matched_competitor_name": "Competitor A" },
      { "position": 4, "title": "Competitor B beans", "asin": "B0BBB", "matched_competitor_name": "Competitor B" },
      { "position": 9, "title": "Competitor C beans", "asin": "B0CCC", "matched_competitor_name": "Competitor C" }
    ]
  }
]`;

export function CompetitorWorkflow({ productId }: CompetitorWorkflowProps) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [productName, setProductName] = useState("Product");
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<CompetitorUploadRecord | null>(null);
  const [rows, setRows] = useState<CompetitorCleanedRow[]>([]);
  const [competitorsText, setCompetitorsText] = useState("");
  const [evidenceText, setEvidenceText] = useState(sampleEvidence);
  const [campaignPlan, setCampaignPlan] = useState<CampaignGenerationResponse | null>(null);
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

  async function loadProduct() {
    setIsLoading(true);
    setMessage(null);
    try {
      const product = await getProductProfile(productId, workspaceId);
      setProductName(product.product_name);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Product could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshRows(uploadId = upload?.id) {
    if (!uploadId) return;
    const response = await getCompetitorCleanedRows(uploadId, 1, 50, workspaceId);
    setRows(response.rows);
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
      setRows(response.cleaned_rows);
      setCampaignPlan(null);
      setMessage(`Uploaded and cleaned ${response.total_rows} rows.`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Competitor upload failed.");
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
      setMessage(caught instanceof Error ? caught.message : "Scoring failed.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleVerify() {
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
      const evidenceRows = JSON.parse(evidenceText || "[]") as CompetitorVerificationEvidenceRow[];
      const response = await verifyCompetitorKeywords(upload.id, { competitors, evidence_rows: evidenceRows, required_match_count: 3 }, workspaceId);
      setRows(response.preview_rows);
      setMessage(`Verified ${response.verified_count} rows. ${response.unverified_count} rows remain unverified.`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Verification failed.");
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
      setMessage(`Generated ${response.campaign_count} approval-controlled campaigns.`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Campaign generation failed.");
    } finally {
      setIsWorking(false);
    }
  }

  if (isLoading) return <LoadingSpinner message="Loading competitor workflow" subtext="Fetching product defaults" />;

  return (
    <div className="space-y-5">
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Competitor research CSV
            <input
              accept=".csv"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-full file:border-0 file:bg-slate-950 file:px-3 file:py-1 file:text-white dark:border-white/10 dark:bg-white/5 dark:text-white dark:file:bg-white dark:file:text-slate-950"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              type="file"
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Workspace ID
            <input className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
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

      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="grid gap-4 lg:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Original competitors
            <textarea className="min-h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setCompetitorsText(event.target.value)} placeholder="Competitor A, Competitor B, Competitor C" value={competitorsText} />
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Top-result evidence JSON
            <textarea className="min-h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setEvidenceText(event.target.value)} value={evidenceText} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button className="inline-flex items-center gap-2" disabled={!upload || isWorking} onClick={handleVerify} type="button" variant="accent">
            <ShieldCheck aria-hidden="true" size={16} />
            Verify
          </Button>
          <Button className="inline-flex items-center gap-2" disabled={!upload || rowCounts.verified === 0 || isWorking} onClick={handleGenerateCampaigns} type="button" variant="success">
            <Play aria-hidden="true" size={16} />
            Generate campaigns
          </Button>
        </div>
      </div>

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
    </div>
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
