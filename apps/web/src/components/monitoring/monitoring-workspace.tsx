"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { createMonitoringImport, getProductMonitoring, processMonitoringJobs, type MonitoringSummary } from "@/lib/api/monitoring";
import { getUploads, type UploadRecord } from "@/lib/api/uploads";
import { selectClasses } from "@/lib/utils";

export function MonitoringWorkspace({ productId }: { productId: string }) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [selectedUploadId, setSelectedUploadId] = useState("");
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  const processedUploads = useMemo(() => uploads.filter((upload) => upload.status === "processed" && upload.source_type === "amazon_ads_sp_search_term_report"), [uploads]);

  async function load() {
    setMessage(null);
    setIsLoading(true);
    try {
      const loadedUploads = await getUploads({ productId, workspaceId });
      const loadedSummary = await getProductMonitoring(productId, workspaceId);
      setUploads(loadedUploads);
      setSummary(loadedSummary);
      setSelectedUploadId((current) => current || loadedUploads.find((upload) => upload.status === "processed")?.id || "");
    } catch (caught) {
      setMessage(formatApiError(caught, "Monitoring data could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  async function importReport() {
    if (!selectedUploadId) {
      setMessage("Choose a processed Sponsored Products Search Term upload before importing metrics.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      await createMonitoringImport(productId, selectedUploadId, workspaceId);
      if (process.env.NODE_ENV !== "production") {
        await processMonitoringJobs(workspaceId);
      }
      await load();
    } catch (caught) {
      setMessage(formatApiError(caught, "Monitoring import failed."));
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {isLoading && !summary ? (
        <LoadingSpinner message="Loading monitoring workspace" subtext="Fetching uploads and monitoring summary" />
      ) : (
        <>
      <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Workspace ID
            <input className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Processed SP Search Term upload
            <select className={`block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white ${selectClasses}`} onChange={(event) => setSelectedUploadId(event.target.value)} value={selectedUploadId}>
              <option value="">Choose processed upload</option>
              {processedUploads.map((upload) => (
                <option key={upload.id} value={upload.id}>
                  {upload.original_filename}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <Button disabled={!selectedUploadId || isLoading} onClick={importReport} type="button" variant="primary">
              {isLoading ? <LoadingSpinner iconOnly size="sm" /> : null}
              Import metrics
            </Button>
            <Button disabled={isLoading} onClick={load} type="button" variant="secondary">
              Refresh
            </Button>
          </div>
        </div>
        {message ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-300/10 dark:text-red-100">{message}</p> : null}
      </div>

      {summary?.agent_summary ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100">
          <p className="font-semibold">{summary.agent_summary.headline}</p>
          {summary.agent_summary.dashboard_summary ? <p className="mt-1">{summary.agent_summary.dashboard_summary}</p> : null}
          <p className="mt-1">{summary.agent_summary.stakeholder_note}</p>
          <p className="mt-2 font-medium">{summary.agent_summary.next_step}</p>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Pending approval" value={summary?.recommendation_counts.pending_approval ?? 0} />
        <Metric label="Keep running" value={summary?.recommendation_counts.keep_running ?? 0} />
        <Metric label="Increase bids" value={summary?.recommendation_counts.increase_bid ?? 0} />
        <Metric label="Decrease bids" value={summary?.recommendation_counts.decrease_bid ?? 0} />
        <Metric label="Pause reviews" value={summary?.recommendation_counts.pause_review ?? 0} />
        <Metric label="Negative exact" value={summary?.recommendation_counts.add_negative_exact ?? 0} />
        <Metric label="Negative phrase" value={summary?.recommendation_counts.add_negative_phrase ?? 0} />
        <Metric label="Move to exact" value={summary?.recommendation_counts.move_to_exact ?? 0} />
        <Metric label="Watch locks" value={summary?.recommendation_counts.watch_lock ?? 0} />
        <Metric label="Data quality" value={summary?.recommendation_counts.data_quality_review ?? 0} />
        <Metric label="Budget reviews" value={summary?.recommendation_counts.budget_review ?? 0} />
      </div>

      <div className="rounded-md border border-slate-200 bg-white dark:border-white/10 dark:bg-slate-950/70">
        <div className="border-b border-slate-200 px-5 py-4 dark:border-white/10">
          <p className="text-sm font-medium text-slate-900 dark:text-white">Monitoring imports</p>
        </div>
        {summary?.imports.length ? (
          <ul className="divide-y divide-slate-200 dark:divide-white/10">
            {summary.imports.map((item) => (
              <li className="px-5 py-4" key={item.id}>
                <p className="font-medium text-slate-950 dark:text-white">{item.report_type} / {item.status}</p>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  {item.processed_rows} processed rows / {item.error_rows} warnings / {item.date_range_start ?? "unknown"} to {item.date_range_end ?? "unknown"}
                </p>
                {item.error_message ? <p className="mt-1 text-sm text-red-700 dark:text-red-300">{item.error_message}</p> : null}
                {!item.error_message && item.data_quality_warnings_json.length ? <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{String(item.data_quality_warnings_json[0].message ?? item.data_quality_warnings_json[0].code ?? "Data quality warning")}</p> : null}
                <Link className="mt-2 inline-block text-sm font-medium text-slate-950 underline dark:text-white" href={`/products/${productId}/monitoring/${item.id}/agents`}>
                  Open Agent Control Center
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 py-8 text-sm text-slate-600 dark:text-slate-300">No monitoring imports yet.</p>
        )}
      </div>

      <RecommendationPreview recommendations={summary?.top_recommendations ?? []} />
        </>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-white">{value}</p>
    </div>
  );
}

function RecommendationPreview({ recommendations }: { recommendations: MonitoringSummary["top_recommendations"] }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white dark:border-white/10 dark:bg-slate-950/70">
      <div className="border-b border-slate-200 px-5 py-4 dark:border-white/10">
        <p className="text-sm font-medium text-slate-900 dark:text-white">Top recommendations</p>
      </div>
      {recommendations.length ? (
        <ul className="divide-y divide-slate-200 dark:divide-white/10">
          {recommendations.map((recommendation) => (
            <li className="px-5 py-4" key={recommendation.id}>
              <p className="font-medium text-slate-950 dark:text-white">{recommendation.recommendation_type} / {recommendation.priority}</p>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{recommendation.campaign_name} / {recommendation.ad_group_name} / {recommendation.customer_search_term}</p>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{recommendation.evidence_json.decision_source === "deepseek_ai" ? "DeepSeek AI" : "Fallback rules"} / {recommendation.rule_name}</p>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{recommendation.explanation_json.summary}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Requires human approval / No live Amazon Ads change executed</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-5 py-8 text-sm text-slate-600 dark:text-slate-300">No recommendations have been generated.</p>
      )}
    </div>
  );
}
