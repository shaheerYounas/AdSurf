"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { createMonitoringImport, getProductMonitoring, processMonitoringJobs, runMonitoringAnalysis, type MonitoringImport, type MonitoringSummary } from "@/lib/api/monitoring";
import { getUploads, type UploadRecord } from "@/lib/api/uploads";
import { selectClasses } from "@/lib/utils";

type IssueCounts = {
  info: number;
  warning: number;
  error: number;
  critical: number;
};

export function MonitoringWorkspace({ productId }: { productId: string }) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [selectedUploadId, setSelectedUploadId] = useState("");
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageTone, setMessageTone] = useState<"info" | "error">("info");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  const processedUploads = useMemo(() => uploads.filter((upload) => upload.status === "processed" && upload.source_type === "amazon_ads_sp_search_term_report"), [uploads]);
  const selectedUploadImport = useMemo(
    () => summary?.imports.find((item) => item.upload_id === selectedUploadId) ?? null,
    [selectedUploadId, summary?.imports],
  );

  async function load() {
    setMessage(null);
    setIsLoading(true);
    try {
      const loadedUploads = await getUploads({ productId, workspaceId });
      const loadedSummary = await getProductMonitoring(productId, workspaceId);
      setUploads(loadedUploads);
      setSummary(loadedSummary);
      setSelectedUploadId(
        (current) =>
          current ||
          loadedUploads.find((upload) => upload.status === "processed" && upload.source_type === "amazon_ads_sp_search_term_report")?.id ||
          "",
      );
    } catch (caught) {
      setMessageTone("error");
      setMessage(formatApiError(caught, "Monitoring data could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  async function importReport() {
    if (!selectedUploadId) {
      setMessageTone("error");
      setMessage("Choose a processed Sponsored Products Search Term upload before importing metrics.");
      return;
    }
    setMessage(null);
    setIsLoading(true);
    try {
      const result = await createMonitoringImport(productId, selectedUploadId, workspaceId);
      if (result.already_imported) {
        setMessageTone("info");
        setMessage(result.message || "This upload was already imported. View the existing import or re-run analysis intentionally.");
      }
      if (process.env.NODE_ENV !== "production") {
        await processMonitoringJobs(workspaceId);
      }
      await load();
    } catch (caught) {
      setMessageTone("error");
      setMessage(formatApiError(caught, "Monitoring import failed."));
      setIsLoading(false);
    }
  }

  async function rerunAnalysis(importRecord: MonitoringImport) {
    setMessage(null);
    setIsLoading(true);
    try {
      const result = await runMonitoringAnalysis(importRecord.id, workspaceId);
      if (process.env.NODE_ENV !== "production") {
        await processMonitoringJobs(workspaceId);
      }
      setMessageTone("info");
      setMessage(result.job_created ? "Analysis was queued for this existing import. No duplicate import was created." : "This import already has analysis available. No duplicate import was created.");
      await load();
    } catch (caught) {
      setMessageTone("error");
      setMessage(formatApiError(caught, "Monitoring analysis could not be queued."));
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
            <input
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white"
              id="monitoring-workspace-id"
              name="workspace_id"
              onChange={(event) => setWorkspaceId(event.target.value)}
              value={workspaceId}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Processed SP Search Term upload
            <select
              className={`block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white ${selectClasses}`}
              id="monitoring-upload-id"
              name="upload_id"
              onChange={(event) => setSelectedUploadId(event.target.value)}
              value={selectedUploadId}
            >
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
        {selectedUploadImport ? (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100">
            <span>This upload was already imported.</span>
            <Link className="font-medium underline" href={`/products/${productId}/monitoring/${selectedUploadImport.id}/agents`}>
              View existing import
            </Link>
            <Button disabled={isLoading} onClick={() => rerunAnalysis(selectedUploadImport)} size="sm" type="button" variant="secondary">
              Re-run analysis
            </Button>
          </div>
        ) : null}
        {message ? (
          <p
            className={`mt-3 rounded-md px-3 py-2 text-sm ${
              messageTone === "error"
                ? "bg-red-50 text-red-700 dark:bg-red-300/10 dark:text-red-100"
                : "bg-sky-50 text-sky-800 dark:bg-sky-300/10 dark:text-sky-100"
            }`}
          >
            {message}
          </p>
        ) : null}
      </div>

      <AnalysisSummary summary={summary} />

      {summary?.agent_summary ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100">
          <p className="font-semibold">{summary.agent_summary.headline}</p>
          {summary.agent_summary.dashboard_summary ? <p className="mt-1">{summary.agent_summary.dashboard_summary}</p> : null}
          <p className="mt-1">{summary.agent_summary.stakeholder_note}</p>
          <p className="mt-2 font-medium">{summary.agent_summary.next_step}</p>
        </div>
      ) : null}

      <RecommendationBreakdown summary={summary} />

      <ProductDetection summary={summary} />

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
                  {item.processed_rows} processed rows / {item.date_range_start ?? "unknown"} to {item.date_range_end ?? "unknown"}
                </p>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Import health: {importHealth(item)} / {issueSummary(item.data_quality_warnings_json)}
                </p>
                {item.error_message ? <p className="mt-1 text-sm text-red-700 dark:text-red-300">{item.error_message}</p> : null}
                {!item.error_message && firstHumanMessage(item) ? <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{firstHumanMessage(item)}</p> : null}
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

function AnalysisSummary({ summary }: { summary: MonitoringSummary | null }) {
  const metrics = summary?.summary_metrics ?? {};
  const rows = metrics.rows_analyzed ?? 0;
  const pending = metrics.pending_human_review ?? summary?.recommendation_counts.pending_approval ?? 0;
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
      <div className="space-y-1">
        <p className="text-sm font-semibold text-slate-900 dark:text-white">Analysis summary</p>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {rows.toLocaleString()} report rows analyzed. {pending.toLocaleString()} recommendations generated for human review. No Amazon Ads changes have been made.
        </p>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Spend reviewed" value={formatMoney(metrics.total_spend)} hint="Uploaded report spend" />
        <Metric label="Sales attributed" value={formatMoney(metrics.total_sales)} hint="Uploaded report sales" />
        <Metric label="Account ACOS" value={formatPercent(metrics.overall_acos)} hint="Spend divided by sales" />
        <Metric label="Zero-order spend" value={formatMoney(metrics.zero_order_spend)} hint="Spend on terms with no orders" />
        <Metric label="Actionable recs" value={metrics.actionable_recommendations ?? 0} hint="Approval-gated actions" />
        <Metric label="Detected products" value={metrics.detected_products ?? 0} hint="Advertised ASIN/SKU groups" />
      </div>
    </section>
  );
}

function RecommendationBreakdown({ summary }: { summary: MonitoringSummary | null }) {
  const counts = summary?.recommendation_counts ?? {};
  const actionCounts = summary?.action_recommendation_counts ?? {};
  const insightCounts = summary?.non_action_insight_counts ?? {};
  return (
    <section className="space-y-3">
      <div>
        <p className="text-sm font-semibold text-slate-900 dark:text-white">Recommendation breakdown</p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          {(summary?.summary_metrics.actionable_recommendations ?? 0).toLocaleString()} actionable recommendations / {(summary?.summary_metrics.watch_insights ?? 0).toLocaleString()} watch insights / {(summary?.summary_metrics.data_quality_checks ?? 0).toLocaleString()} data quality checks / {(summary?.summary_metrics.budget_review_notes ?? 0).toLocaleString()} budget review notes
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Pending approval" value={counts.pending_approval ?? 0} hint="Needs human review" />
        <Metric label="Increase bids" value={actionCounts.increase_bid ?? 0} hint="Conversion-backed only" />
        <Metric label="Decrease bids" value={actionCounts.decrease_bid ?? 0} hint="High ACOS with evidence" />
        <Metric label="Pause reviews" value={actionCounts.pause_review ?? 0} hint="Review-only action" />
        <Metric label="Negative exact" value={actionCounts.add_negative_exact ?? 0} hint="Spend/click threshold met" />
        <Metric label="Negative phrase" value={actionCounts.add_negative_phrase ?? 0} hint="Broad pattern waste" />
        <Metric label="Move to exact" value={actionCounts.move_to_exact ?? 0} hint="Efficient non-exact term" />
        <Metric label="Keep running" value={insightCounts.keep_running ?? 0} hint="No action needed" />
        <Metric label="Watch locks" value={insightCounts.watch_lock ?? 0} hint="Monitor without action" />
        <Metric label="Data quality" value={counts.data_quality_review ?? 0} hint="Check before optimizing" />
        <Metric label="Budget reviews" value={counts.budget_review ?? 0} hint="Review budget pressure" />
      </div>
    </section>
  );
}

function ProductDetection({ summary }: { summary: MonitoringSummary | null }) {
  const groups = summary?.detected_product_groups ?? [];
  if (!groups.length) return null;
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
      <p className="text-sm font-semibold text-slate-900 dark:text-white">Detected product groups</p>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        Product grouping uses advertised ASIN/SKU columns only. Customer Search Term ASINs are not used to create product profiles.
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {groups.slice(0, 6).map((group) => (
          <div className="rounded-md border border-slate-200 p-4 dark:border-white/10" key={group.key}>
            <p className="font-mono text-sm font-semibold text-slate-950 dark:text-white">{group.asin || group.sku || group.key}</p>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {group.rows.toLocaleString()} rows / {formatMoney(group.spend)} spend / {group.orders.toLocaleString()} orders
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-white">{typeof value === "number" ? value.toLocaleString() : value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p> : null}
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
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                {recommendation.evidence_json.decision_source === "deepseek_ai" ? "DeepSeek AI" : "Deterministic rules"} / {confidenceLabel(recommendation.confidence)} confidence
              </p>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{recommendation.explanation_json.summary}</p>
              {typeof recommendation.explanation_json.evidence === "string" ? <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{recommendation.explanation_json.evidence}</p> : null}
              <details className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                <summary className="cursor-pointer font-medium text-slate-600 dark:text-slate-300">Advanced details</summary>
                <p className="mt-1">Rule: {String((recommendation.explanation_json as { advanced_details?: { rule?: unknown } }).advanced_details?.rule ?? recommendation.rule_name)}</p>
              </details>
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

function formatMoney(value: string | number | null | undefined) {
  const amount = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number.isFinite(amount) ? amount : 0);
}

function formatPercent(value: string | number | null | undefined) {
  if (value === null || value === undefined) return "n/a";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "n/a";
  return `${(amount * 100).toFixed(2)}%`;
}

function confidenceLabel(value: string) {
  return value.replace(/_/g, " ");
}

function issueSummary(messages: Array<Record<string, unknown>>) {
  const counts = issueCounts(messages);
  return `${counts.info} info message${counts.info === 1 ? "" : "s"} / ${counts.warning} warning${counts.warning === 1 ? "" : "s"} / ${counts.error + counts.critical} blocking issue${counts.error + counts.critical === 1 ? "" : "s"}`;
}

function importHealth(item: MonitoringImport) {
  const counts = issueCounts(item.data_quality_warnings_json);
  return counts.error + counts.critical === 0 ? "Good" : "Needs review";
}

function firstHumanMessage(item: MonitoringImport) {
  const message = item.data_quality_warnings_json.find((entry) => entry.severity !== "info") || item.data_quality_warnings_json[0];
  return message ? String(message.message ?? message.code ?? "") : "";
}

function issueCounts(messages: Array<Record<string, unknown>>): IssueCounts {
  return messages.reduce<IssueCounts>(
    (counts, message) => {
      const severity = String(message.severity || "warning");
      if (severity === "critical" || severity === "error" || severity === "warning" || severity === "info") {
        counts[severity] += 1;
      } else {
        counts.warning += 1;
      }
      return counts;
    },
    { info: 0, warning: 0, error: 0, critical: 0 },
  );
}
