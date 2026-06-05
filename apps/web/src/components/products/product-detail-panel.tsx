"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, AlertTriangle, BarChart3, CheckCircle2, FileSpreadsheet, Globe, Layers, RefreshCw, Target, Trash2, TrendingUp, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ProductProfile } from "@adsurf/types";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { deleteProductProfile, getProductProfile } from "@/lib/api/products";
import { getUploads, type UploadRecord } from "@/lib/api/uploads";

export function ProductDetailPanel({ productId }: { productId: string }) {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [product, setProduct] = useState<ProductProfile | null>(null);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    loadProduct();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const statusCounts = useMemo(() => {
    return uploads.reduce<Record<string, number>>((counts, upload) => {
      counts[upload.status] = (counts[upload.status] ?? 0) + 1;
      return counts;
    }, {});
  }, [uploads]);

  const latestAdsReport = uploads.find((upload) => upload.status === "processed" && upload.source_type === "amazon_ads_sp_search_term_report");
  const latestCompetitorUpload = uploads.find((upload) => upload.status === "processed" && upload.source_type === "competitor_keyword_research");

  async function loadProduct() {
    setError(null);
    setIsLoading(true);
    try {
      const loadedProduct = await getProductProfile(productId, workspaceId);
      const loadedUploads = await getUploads({ productId, workspaceId });
      setProduct(loadedProduct);
      setUploads(loadedUploads);
    } catch (caught) {
      setError(formatApiError(caught, "Product could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDelete() {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteProductProfile(productId, workspaceId);
      router.push("/products");
      router.refresh();
    } catch (caught) {
      setDeleteError(formatApiError(caught, "Product could not be deleted."));
      setIsDeleting(false);
    }
  }

  if (isLoading) {
    return <LoadingSpinner message="Loading product workflow" subtext="Fetching product profile and upload records" />;
  }

  if (error || !product) {
    return (
      <div className="space-y-3 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100">
        <div className="flex items-center gap-2 font-medium">
          <AlertCircle aria-hidden="true" size={18} />
          Product could not be loaded
        </div>
        <p>{error ?? "Product profile was not found."}</p>
        <div className="flex flex-wrap items-end gap-3">
          <WorkspaceInput onChange={setWorkspaceId} value={workspaceId} />
          <Button className="inline-flex items-center gap-2" onClick={loadProduct} type="button" variant="primary">
            <RefreshCw aria-hidden="true" size={16} />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const totalFiles = uploads.length;
  const processedFiles = statusCounts.processed ?? 0;
  const failedFiles = statusCounts.failed ?? 0;

  return (
    <div className="space-y-6">
      {/* Header card */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/80">
        <div className="bg-gradient-to-r from-indigo-50 via-white to-slate-50 px-6 py-5 dark:from-indigo-950/40 dark:via-slate-950 dark:to-slate-950">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">Product profile</p>
              <h2 className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">{product.product_name}</h2>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                {product.asin && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 font-mono text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200">
                    ASIN: {product.asin}
                  </span>
                )}
                {product.sku && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 font-mono text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200">
                    SKU: {product.sku}
                  </span>
                )}
                <StatusBadge status={product.status} />
              </div>
              <p className="mt-2 font-mono text-[11px] text-slate-400">{product.id}</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <WorkspaceInput onChange={setWorkspaceId} value={workspaceId} />
              <Button className="inline-flex items-center gap-2" onClick={loadProduct} type="button" variant="secondary">
                <RefreshCw aria-hidden="true" size={16} />
                Refresh
              </Button>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-600 transition hover:border-red-300 hover:bg-red-50 dark:border-red-400/30 dark:bg-transparent dark:text-red-400 dark:hover:bg-red-400/10"
              >
                <Trash2 aria-hidden="true" size={15} />
                Delete
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 border-t border-slate-100 sm:grid-cols-3 lg:grid-cols-6 dark:divide-white/10 dark:border-white/10">
          <MetricCell icon={<Globe size={14} />} label="Marketplace" value={product.marketplace} />
          <MetricCell icon={<span className="text-xs font-bold">{product.currency}</span>} label="Currency" value={product.currency} />
          <MetricCell icon={<Target size={14} />} label="Target ACOS" value={product.target_acos != null ? `${product.target_acos}%` : "—"} highlight />
          <MetricCell icon={<TrendingUp size={14} />} label="Default bid" value={product.default_bid != null ? `$${product.default_bid}` : "—"} />
          <MetricCell icon={<BarChart3 size={14} />} label="Default budget" value={product.default_budget != null ? `$${product.default_budget}` : "—"} />
          <MetricCell icon={<Layers size={14} />} label="Total uploads" value={String(totalFiles)} highlight={totalFiles > 0} />
        </div>
      </div>

      {/* Workflow cards */}
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Workflow steps</p>
        <div className="grid gap-3 lg:grid-cols-5">
          <WorkflowCard
            href={`/products/${productId}/uploads`}
            icon={<UploadCloud aria-hidden="true" size={18} />}
            label="Upload research"
            meta={totalFiles ? `${totalFiles} file${totalFiles === 1 ? "" : "s"} uploaded` : "No files yet"}
            status={totalFiles ? "Ready" : "Next step"}
            statusVariant={totalFiles ? "success" : "pending"}
          />
          <WorkflowCard
            href={latestCompetitorUpload ? `/products/${productId}/uploads/${latestCompetitorUpload.id}/mapping` : `/products/${productId}/uploads`}
            icon={<FileSpreadsheet aria-hidden="true" size={18} />}
            label="Map keywords"
            meta={latestCompetitorUpload ? latestCompetitorUpload.original_filename : "Upload a competitor keyword file first"}
            status={latestCompetitorUpload ? "Open" : "Waiting"}
            statusVariant={latestCompetitorUpload ? "success" : "waiting"}
          />
          <WorkflowCard
            href={`/products/${productId}/competitors`}
            icon={<FileSpreadsheet aria-hidden="true" size={18} />}
            label="Verify competitors"
            meta="Manual Amazon result evidence"
            status="Ready"
            statusVariant="success"
          />
          <WorkflowCard
            href={`/products/${productId}/monitoring`}
            icon={<TrendingUp aria-hidden="true" size={18} />}
            label="Monitor ads"
            meta={latestAdsReport ? latestAdsReport.original_filename : "Upload a Search Term report first"}
            status={latestAdsReport ? "Ready" : "Next step"}
            statusVariant={latestAdsReport ? "success" : "pending"}
          />
          <WorkflowCard
            href={latestCompetitorUpload ? `/products/${productId}/uploads/${latestCompetitorUpload.id}/mapping` : `/products/${productId}/uploads`}
            icon={<CheckCircle2 aria-hidden="true" size={18} />}
            label="Campaign export"
            meta="Approval-controlled bulk CSV"
            status={latestCompetitorUpload ? "Available" : "Waiting"}
            statusVariant={latestCompetitorUpload ? "success" : "waiting"}
          />
        </div>
      </div>

      {/* Upload status summary */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/80">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 px-5 py-4 dark:border-white/10">
          <div>
            <p className="text-sm font-semibold text-slate-900 dark:text-white">Uploaded resources</p>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Processed uploads can be opened for mapping, scoring, and campaign generation.</p>
          </div>
          <Link
            className="inline-flex items-center gap-2 rounded-full bg-slate-950 px-4 py-2 text-xs font-semibold text-white transition hover:-translate-y-0.5 hover:bg-slate-800 dark:bg-white/10 dark:hover:bg-white/20"
            href={`/products/${productId}/uploads`}
          >
            <UploadCloud size={14} />
            Manage uploads
          </Link>
        </div>
        <div className="grid grid-cols-2 divide-x divide-y divide-slate-100 sm:grid-cols-4 dark:divide-white/10">
          <UploadStatCell label="Processed" value={processedFiles} variant="success" />
          <UploadStatCell label="Processing" value={statusCounts.processing ?? 0} variant="active" />
          <UploadStatCell label="Queued" value={statusCounts.queued_for_processing ?? 0} variant="pending" />
          <UploadStatCell label="Failed" value={failedFiles} variant={failedFiles > 0 ? "danger" : "neutral"} />
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-product-dialog-title"
        >
          <div
            className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm dark:bg-black/60"
            onClick={() => !isDeleting && setShowDeleteConfirm(false)}
          />
          <div className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-100 text-red-600 dark:bg-red-400/15 dark:text-red-400">
                <AlertTriangle size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="delete-product-dialog-title" className="text-base font-semibold text-slate-900 dark:text-white">
                  Delete product profile?
                </h2>
                <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400">
                  <span className="font-medium text-slate-800 dark:text-slate-200">{product.product_name}</span> and all associated data will be permanently deleted. This cannot be undone.
                </p>
                {deleteError && (
                  <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300">
                    {deleteError}
                  </p>
                )}
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => { setShowDeleteConfirm(false); setDeleteError(null); }}
                disabled={isDeleting}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={isDeleting}
                className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-60 dark:bg-red-500 dark:hover:bg-red-600"
              >
                {isDeleting ? (
                  <>
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Deleting…
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WorkspaceInput({ onChange, value }: { onChange: (value: string) => void; value: string }) {
  return (
    <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
      Workspace ID
      <input id="product-detail-workspace-id" name="product_detail_workspace_id" className="block w-72 rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => onChange(event.target.value)} value={value} />
    </label>
  );
}

function MetricCell({ icon, label, value, highlight }: { icon: ReactNode; label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
        <span className="text-slate-400 dark:text-slate-500">{icon}</span>
        {label}
      </div>
      <p className={`text-sm font-semibold ${highlight ? "text-indigo-700 dark:text-indigo-300" : "text-slate-950 dark:text-white"}`}>{value}</p>
    </div>
  );
}

function UploadStatCell({ label, value, variant }: { label: string; value: number; variant: "success" | "active" | "pending" | "danger" | "neutral" }) {
  const colorMap = {
    success: "text-emerald-600 dark:text-emerald-400",
    active: "text-indigo-600 dark:text-indigo-400",
    pending: "text-amber-600 dark:text-amber-400",
    danger: "text-rose-600 dark:text-rose-400",
    neutral: "text-slate-600 dark:text-slate-400",
  };
  return (
    <div className="px-5 py-4">
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className={`mt-1 text-2xl font-semibold ${colorMap[variant]}`}>{value}</dd>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isActive = status === "active";
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${isActive ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-300/15 dark:text-emerald-200" : "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-300"}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function WorkflowCard({
  href,
  icon,
  label,
  meta,
  status,
  statusVariant,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  meta: string;
  status: string;
  statusVariant: "success" | "pending" | "waiting";
}) {
  const statusColors = {
    success: "text-emerald-700 dark:text-emerald-300",
    pending: "text-indigo-700 dark:text-indigo-300",
    waiting: "text-slate-500 dark:text-slate-400",
  };
  return (
    <Link
      className="block rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md dark:border-white/10 dark:bg-slate-950/70 dark:hover:border-indigo-300/30 dark:hover:shadow-indigo-300/5"
      href={href}
    >
      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">
        {icon}
      </div>
      <p className="mt-3 text-sm font-semibold text-slate-900 dark:text-slate-200">{label}</p>
      <p className={`mt-1 text-base font-semibold ${statusColors[statusVariant]}`}>{status}</p>
      <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{meta}</p>
    </Link>
  );
}
