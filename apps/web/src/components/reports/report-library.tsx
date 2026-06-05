"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArchiveX, BarChart3, CheckCircle2, Database, FileSpreadsheet, Filter, Loader2, RefreshCw, RotateCcw, Search, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Modal } from "@/components/ui/modal";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { listAccountImports, type AccountImportRecord } from "@/lib/api/account-imports";
import { getProductMonitoring, getRecommendations, type MonitoringImport, type Recommendation } from "@/lib/api/monitoring";
import { getProductProfiles } from "@/lib/api/products";
import { archiveUpload, deleteUpload, getUploadParseRuns, getUploads, reprocessUpload, type ParseRun, type UploadRecord } from "@/lib/api/uploads";
import { getCachedData, setCachedData, warmSections } from "@/lib/prefetch";

type ProductLite = {
  id: string;
  product_name: string;
  asin?: string | null;
  marketplace?: string | null;
};

type ReportRow = {
  upload: UploadRecord;
  product?: ProductLite;
  parseRun?: ParseRun;
  accountImport?: AccountImportRecord;
  monitoringImports: MonitoringImport[];
  recommendations: Recommendation[];
};

type StatusFilter = "all" | "processed" | "queued_for_processing" | "failed";

export function ReportLibrary() {
  const [workspaceId] = useState(defaultWorkspaceId);
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  useEffect(() => {
    warmSections(["reports", "uploads", "products", "recommendations"]);
    loadReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadReports() {
    setError(null);
    setIsLoading(true);
    try {
      const uploads = await cachedOrFetch("reports:uploads", () => getUploads({ workspaceId }), 120_000);
      const products = await cachedOrFetch("products:list", () => getProductProfiles(workspaceId), 120_000);
      const accountImports = await cachedOrFetch("reports:account-imports", () => listAccountImports(workspaceId), 120_000);
      const recommendations = await cachedOrFetch("recommendations:list", () => getRecommendations(workspaceId), 60_000);

      const productMap = new Map(products.map((product) => [product.id, product as ProductLite]));
      const accountImportByUploadId = new Map(accountImports.map((record) => [record.upload_id, record]));
      const recommendationsByImportId = groupBy(recommendations, (rec) => rec.monitoring_import_id ?? rec.account_import_id ?? "");

      // Fetch monitoring summaries and parse runs in parallel (was sequential for...of — O(n) → O(1) with Promise.all)
      const [monitoringResults, parseRunResults] = await Promise.all([
        Promise.allSettled(
          products.map(async (product) => {
            const summary = await cachedOrFetch(`monitoring:${product.id}:summary`, () => getProductMonitoring(product.id, workspaceId), 60_000);
            return { productId: product.id, summary };
          }),
        ),
        Promise.allSettled(
          uploads.map(async (upload): Promise<[string, ParseRun | undefined]> => {
            const runs = await cachedOrFetch(`uploads:${upload.id}:parse-runs`, () => getUploadParseRuns(upload.id, workspaceId), 120_000);
            return [upload.id, runs[0]];
          }),
        ),
      ]);

      const monitoringImports = monitoringResults.flatMap((result) => (result.status === "fulfilled" ? result.value.summary?.imports ?? [] : []));
      const monitoringByUploadId = groupBy(monitoringImports, (item) => item.upload_id);

      const parseRunEntries: Array<[string, ParseRun | undefined]> = parseRunResults.map((result) =>
        result.status === "fulfilled" ? result.value : ["", undefined],
      );
      // Filter out failed parse entries
      const parseRunByUploadId = new Map(parseRunEntries.filter(([uploadId]) => uploadId !== ""));

      setRows(
        uploads.map((upload) => {
          const accountImport = accountImportByUploadId.get(upload.id);
          const relatedMonitoring = monitoringByUploadId.get(upload.id) ?? [];
          const relatedRecommendations = [
            ...(accountImport ? recommendationsByImportId.get(accountImport.id) ?? [] : []),
            ...relatedMonitoring.flatMap((item) => recommendationsByImportId.get(item.id) ?? []),
          ];
          return {
            upload,
            product: upload.product_id ? productMap.get(upload.product_id) : undefined,
            parseRun: parseRunByUploadId.get(upload.id),
            accountImport,
            monitoringImports: relatedMonitoring,
            recommendations: dedupeById(relatedRecommendations),
          };
        }),
      );
    } catch (caught) {
      setError(formatApiError(caught, "Report library could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  const sourceOptions = useMemo(() => Array.from(new Set(rows.map((row) => row.upload.source_type))).sort(), [rows]);
  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (statusFilter !== "all" && row.upload.status !== statusFilter) return false;
      if (sourceFilter !== "all" && row.upload.source_type !== sourceFilter) return false;
      if (!normalizedQuery) return true;
      const haystack = [
        row.upload.original_filename,
        row.upload.source_type,
        row.upload.status,
        row.product?.product_name,
        row.product?.asin,
        row.accountImport?.detected_report_type,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [query, rows, sourceFilter, statusFilter]);

  const processedCount = rows.filter((row) => row.upload.status === "processed").length;
  const recommendationCount = rows.reduce((count, row) => count + row.recommendations.length, 0);
  const warningCount = rows.reduce((count, row) => count + (row.parseRun?.error_rows_count ?? 0) + (row.accountImport?.error_rows ?? 0), 0);

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Workspace reports</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">Uploaded report library</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
            Inspect every uploaded file in this workspace and see the parse run, detected account import, monitoring import, and recommendation records connected to it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-slate-200 bg-white px-3 py-2 font-mono text-xs font-semibold text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">{workspaceId}</span>
          <Button disabled={isLoading} onClick={loadReports} type="button" variant="secondary">
            {isLoading ? <Loader2 aria-hidden="true" className="animate-spin" size={14} /> : <RefreshCw aria-hidden="true" size={14} />}
            Refresh
          </Button>
        </div>
      </div>

      <div className="rounded-2xl border border-indigo-200 bg-[linear-gradient(135deg,#eef2ff,#f8fafc_42%,#ecfeff)] p-5 shadow-sm dark:border-white/10 dark:bg-[linear-gradient(135deg,#020617,#0f172a_45%,#111827)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-200">Manage uploaded resources</p>
            <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">Open the right view for each uploaded file</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
              Use these entry points to inspect uploads, continue workflows, and jump into downstream analysis without losing workspace context.
            </p>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400">{rows.length} uploaded resources tracked in this workspace</p>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <ResourceActionCard href="/products" title="Product hubs" description="Review product profiles and upload status by catalog." />
          <ResourceActionCard href="/reports" title="Report library" description="Search files, parse runs, and connected analysis records." />
          <ResourceActionCard href="/recommendations" title="Recommendation queue" description="Review rule output generated from uploaded and monitored data." />
          <ResourceActionCard href="/agents" title="Workflow console" description="Continue uploads, parsing, and campaign review in one place." />
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <SummaryCard icon={<FileSpreadsheet size={16} />} label="Total files" value={rows.length} />
        <SummaryCard icon={<CheckCircle2 size={16} />} label="Processed" value={processedCount} />
        <SummaryCard icon={<BarChart3 size={16} />} label="Recommendations" value={recommendationCount} />
        <SummaryCard icon={<AlertTriangle size={16} />} label="Warnings / row errors" value={warningCount} />
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950/80 lg:flex-row lg:items-center">
        <label className="relative min-w-0 flex-1">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <span className="sr-only">Search reports</span>
          <input
            className="min-h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-950 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-white/5 dark:text-white dark:focus:ring-indigo-300/20"
            id="report-library-search"
            name="report_library_search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search filename, product, report type"
            value={query}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <Filter aria-hidden="true" className="mt-2 text-slate-400" size={16} />
          <select id="report-status-filter" name="report_status_filter" className="min-h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 dark:border-white/10 dark:bg-slate-900 dark:text-slate-100" onChange={(event) => setStatusFilter(event.target.value as StatusFilter)} value={statusFilter}>
            <option value="all">All statuses</option>
            <option value="processed">Processed</option>
            <option value="queued_for_processing">Queued</option>
            <option value="failed">Failed</option>
          </select>
          <select id="report-source-filter" name="report_source_filter" className="min-h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 dark:border-white/10 dark:bg-slate-900 dark:text-slate-100" onChange={(event) => setSourceFilter(event.target.value)} value={sourceFilter}>
            <option value="all">All report types</option>
            {sourceOptions.map((source) => (
              <option key={source} value={source}>{humanize(source)}</option>
            ))}
          </select>
        </div>
      </div>

      {error ? <ErrorNotice actionLabel="Reload reports" message={error} onAction={loadReports} title="Report library could not be refreshed" /> : null}

      {isLoading ? (
        <LoadingSpinner message="Loading report library" subtext="Fetching uploads, parse runs, imports, and recommendation links" />
      ) : filteredRows.length ? (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/90">
          <div className="grid grid-cols-[minmax(260px,1.4fr)_minmax(160px,0.8fr)_minmax(220px,1fr)_minmax(220px,1fr)_auto] gap-4 border-b border-slate-100 px-5 py-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500 dark:border-white/10 dark:text-slate-400 max-lg:hidden">
            <span>File</span>
            <span>Status</span>
            <span>Parsed data</span>
            <span>Related analysis</span>
            <span>Actions</span>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-white/10">
            {filteredRows.map((row) => (
              <ReportRowItem key={row.upload.id} row={row} workspaceId={workspaceId} onDeleted={(id) => setRows((prev) => prev.filter((r) => r.upload.id !== id))} onStatusChanged={(id, status) => setRows((prev) => prev.map((r) => r.upload.id === id ? { ...r, upload: { ...r.upload, status } } : r))} />
            ))}
          </ul>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center dark:border-white/15 dark:bg-slate-950/70">
          <Database aria-hidden="true" className="mx-auto text-slate-400" size={28} />
          <p className="mt-3 text-sm font-semibold text-slate-950 dark:text-white">No reports match these filters.</p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Upload an Amazon Ads report or clear the filters to inspect existing records.</p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-100">
        <ShieldCheck aria-hidden="true" size={17} />
        <span className="font-semibold">Review and routing hub.</span>
        <span>This screen helps you manage uploaded resources and navigate to the right workflow without executing Amazon Ads changes.</span>
      </div>
    </section>
  );
}

async function cachedOrFetch<T>(cacheKey: string, fetcher: () => Promise<T>, ttlMs: number): Promise<T> {
  const cached = getCachedData<T>(cacheKey);
  if (cached !== null) return cached;
  const data = await fetcher();
  setCachedData(cacheKey, data, ttlMs);
  return data;
}

function ReportRowItem({
  row,
  workspaceId,
  onDeleted,
  onStatusChanged,
}: {
  row: ReportRow;
  workspaceId: string;
  onDeleted: (id: string) => void;
  onStatusChanged: (id: string, status: string) => void;
}) {
  const upload = row.upload;
  const latestMonitoring = row.monitoringImports[0];
  const isSpSearchTermReport = upload.source_type === "amazon_ads_sp_search_term_report";
  const workflowHref = upload.product_id
    ? isSpSearchTermReport
      ? `/products/${upload.product_id}/monitoring`
      : `/products/${upload.product_id}/uploads/${upload.id}/mapping`
    : "/agents#reports";
  const workflowLabel = isSpSearchTermReport ? "Open monitoring" : "Open workflow";
  const monitoringHref = upload.product_id ? `/products/${upload.product_id}/monitoring` : "/agents";

  const [pendingAction, setPendingAction] = useState<"delete" | "archive" | "reprocess" | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function handleConfirm() {
    if (!pendingAction) return;
    setIsSubmitting(true);
    setActionError(null);
    try {
      if (pendingAction === "delete") {
        await deleteUpload(upload.id, workspaceId);
        setPendingAction(null);
        onDeleted(upload.id);
      } else if (pendingAction === "archive") {
        const updated = await archiveUpload(upload.id, workspaceId);
        setPendingAction(null);
        onStatusChanged(upload.id, updated.status);
      } else if (pendingAction === "reprocess") {
        const result = await reprocessUpload(upload.id, workspaceId);
        setPendingAction(null);
        onStatusChanged(upload.id, result.upload.status);
      }
    } catch (err) {
      setActionError(formatApiError(err, "Action failed. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }

  const isProcessing = upload.status === "processing";
  const isArchived = upload.status === "archived";

  const modalConfig = {
    delete: {
      title: "Delete upload permanently",
      description: "This will permanently remove the file, parse run, account import, monitoring data, and all associated records. This action cannot be undone.",
      confirmLabel: "Delete permanently",
      confirmVariant: "danger" as const,
    },
    archive: {
      title: "Archive upload",
      description: "Archiving will hide this upload from active workflows. The record is preserved but marked inactive. You can reprocess it later if needed.",
      confirmLabel: "Archive upload",
      confirmVariant: "warning" as const,
    },
    reprocess: {
      title: "Reprocess upload",
      description: "This will clear all existing parse runs, imports, and monitoring data for this upload, then re-queue it for processing from scratch.",
      confirmLabel: "Reprocess upload",
      confirmVariant: "primary" as const,
    },
  };

  return (
    <>
      <li className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(260px,1.4fr)_minmax(160px,0.8fr)_minmax(220px,1fr)_minmax(220px,1fr)_auto]">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950 dark:text-white">{upload.original_filename}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{humanize(upload.source_type)} / {formatBytes(upload.file_size_bytes)}</p>
          <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">{row.product ? `${row.product.product_name}${row.product.asin ? ` / ${row.product.asin}` : ""}` : "Account-level report"}</p>
          <p className="mt-2 font-mono text-[11px] text-slate-400">{upload.id}</p>
        </div>
        <div>
          <StatusPill status={upload.status} />
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Uploaded {formatDate(upload.created_at)}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Confirmed {upload.confirmed_at ? formatDate(upload.confirmed_at) : "not yet"}</p>
        </div>
        <div className="space-y-2 text-sm">
          {row.parseRun ? (
            <>
              <MetricLine label="Parse status" value={humanize(row.parseRun.status)} />
              <MetricLine label="Rows" value={`${formatNumber(row.parseRun.parsed_rows_count)} parsed / ${formatNumber(row.parseRun.error_rows_count)} errors`} />
              <MetricLine label="Columns" value={formatNumber(row.parseRun.total_columns)} />
            </>
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">No parse run recorded.</p>
          )}
          <Link className="inline-flex text-xs font-semibold text-indigo-600 hover:text-indigo-500 dark:text-indigo-200" href={workflowHref}>
            {workflowLabel}
          </Link>
        </div>
        <div className="space-y-2 text-sm">
          {row.accountImport ? <MetricLine label="Account import" value={`${humanize(row.accountImport.status)} / ${humanize(row.accountImport.detected_report_type)}`} /> : null}
          {latestMonitoring ? <MetricLine label="Monitoring import" value={`${humanize(latestMonitoring.status)} / ${formatNumber(latestMonitoring.processed_rows)} rows`} /> : null}
          <MetricLine label="Recommendations" value={formatNumber(row.recommendations.length)} />
          <div className="flex flex-wrap gap-2 pt-1">
            {upload.product_id ? <Link className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200" href={`/products/${upload.product_id}`}>Product</Link> : null}
            {upload.product_id ? <Link className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200" href={monitoringHref}>Monitoring</Link> : null}
            {row.recommendations.length ? <Link className="rounded-full bg-indigo-100 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-300/15 dark:text-indigo-100" href="/recommendations">Recommendations</Link> : null}
          </div>
        </div>
        <div className="flex flex-row items-start gap-2 lg:flex-col lg:items-end">
          <button
            type="button"
            title="Reprocess upload"
            disabled={isProcessing}
            onClick={() => setPendingAction("reprocess")}
            className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-indigo-300/20 dark:bg-indigo-300/10 dark:text-indigo-200 dark:hover:bg-indigo-300/20"
          >
            <RotateCcw size={12} />
            Reprocess
          </button>
          {!isArchived && (
            <button
              type="button"
              title="Archive upload"
              disabled={isProcessing}
              onClick={() => setPendingAction("archive")}
              className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-200 dark:hover:bg-amber-300/20"
            >
              <ArchiveX size={12} />
              Archive
            </button>
          )}
          <button
            type="button"
            title="Delete upload"
            disabled={isProcessing}
            onClick={() => setPendingAction("delete")}
            className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-rose-300/20 dark:bg-rose-300/10 dark:text-rose-300 dark:hover:bg-rose-300/20"
          >
            <Trash2 size={12} />
            Delete
          </button>
        </div>
      </li>

      {pendingAction && (
        <Modal
          open
          onClose={() => { if (!isSubmitting) { setPendingAction(null); setActionError(null); } }}
          title={modalConfig[pendingAction].title}
          description={modalConfig[pendingAction].description}
          size="sm"
        >
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 dark:border-white/10 dark:bg-white/5">
              <p className="truncate text-sm font-semibold text-slate-950 dark:text-white">{upload.original_filename}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{humanize(upload.source_type)} · {formatBytes(upload.file_size_bytes)}</p>
              <p className="mt-1 font-mono text-[11px] text-slate-400">{upload.id}</p>
            </div>
            {actionError && (
              <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-300/20 dark:bg-rose-300/10 dark:text-rose-200">{actionError}</p>
            )}
            <div className="flex justify-end gap-3">
              <Button disabled={isSubmitting} onClick={() => { setPendingAction(null); setActionError(null); }} type="button" variant="secondary" size="sm">
                Cancel
              </Button>
              <Button disabled={isSubmitting} onClick={handleConfirm} type="button" variant={modalConfig[pendingAction].confirmVariant} size="sm">
                {isSubmitting ? <Loader2 aria-hidden="true" className="animate-spin" size={13} /> : null}
                {modalConfig[pendingAction].confirmLabel}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

function SummaryCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950/80">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-indigo-600 dark:bg-white/10 dark:text-indigo-200">{icon}</span>
        {label}
      </div>
      <p className="mt-3 text-2xl font-semibold text-slate-950 dark:text-white">{formatNumber(value)}</p>
    </div>
  );
}

function ResourceActionCard({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <Link className="rounded-2xl border border-white/60 bg-white/90 p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md dark:border-white/10 dark:bg-slate-950/75 dark:hover:border-indigo-300/30" href={href}>
      <p className="text-sm font-semibold text-slate-950 dark:text-white">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{description}</p>
    </Link>
  );
}

function StatusPill({ status }: { status: string }) {
  const ok = status === "processed" || status === "succeeded";
  const failed = status === "failed";
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${ok ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-300/15 dark:text-emerald-100" : failed ? "bg-rose-100 text-rose-800 dark:bg-rose-300/15 dark:text-rose-100" : "bg-amber-100 text-amber-800 dark:bg-amber-300/15 dark:text-amber-100"}`}>
      {humanize(status)}
    </span>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <p className="flex justify-between gap-3 text-xs">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="text-right font-semibold text-slate-800 dark:text-slate-100">{value}</span>
    </p>
  );
}

function groupBy<T>(items: T[], getKey: (item: T) => string): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const key = getKey(item);
    if (!key) continue;
    map.set(key, [...(map.get(key) ?? []), item]);
  }
  return map;
}

function dedupeById<T extends { id: string }>(items: T[]): T[] {
  return Array.from(new Map(items.map((item) => [item.id, item])).values());
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function formatNumber(value: number) {
  return value.toLocaleString("en-US");
}
