"use client";

import Link from "next/link";
import { AlertCircle, CheckCircle2, FileSpreadsheet, RefreshCw, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ProductProfile } from "@adsurf/types";
import { Button } from "@/components/ui/button";
import { defaultWorkspaceId } from "@/lib/api/client";
import { getProductProfile } from "@/lib/api/products";
import { getUploads, type UploadRecord } from "@/lib/api/uploads";

export function ProductDetailPanel({ productId }: { productId: string }) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [product, setProduct] = useState<ProductProfile | null>(null);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadProduct();
  }, []);

  const statusCounts = useMemo(() => {
    return uploads.reduce<Record<string, number>>((counts, upload) => {
      counts[upload.status] = (counts[upload.status] ?? 0) + 1;
      return counts;
    }, {});
  }, [uploads]);

  const latestProcessedUpload = uploads.find((upload) => upload.status === "processed");

  async function loadProduct() {
    setError(null);
    setIsLoading(true);
    try {
      const [loadedProduct, loadedUploads] = await Promise.all([
        getProductProfile(productId, workspaceId),
        getUploads({ productId, workspaceId }),
      ]);
      setProduct(loadedProduct);
      setUploads(loadedUploads);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Product could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  if (isLoading) {
    return <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-600">Loading product workflow...</div>;
  }

  if (error || !product) {
    return (
      <div className="space-y-3 rounded-md border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        <div className="flex items-center gap-2 font-medium">
          <AlertCircle aria-hidden="true" size={18} />
          Product could not be loaded
        </div>
        <p>{error ?? "Product profile was not found."}</p>
        <div className="flex flex-wrap items-end gap-3">
          <WorkspaceInput onChange={setWorkspaceId} value={workspaceId} />
          <Button className="inline-flex items-center gap-2" onClick={loadProduct} type="button">
            <RefreshCw aria-hidden="true" size={16} />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Product profile</p>
            <h3 className="mt-1 text-2xl font-semibold tracking-normal text-slate-950">{product.product_name}</h3>
            <p className="mt-2 font-mono text-xs text-slate-500">{product.id}</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <WorkspaceInput onChange={setWorkspaceId} value={workspaceId} />
            <Button className="inline-flex items-center gap-2 bg-slate-700" onClick={loadProduct} type="button">
              <RefreshCw aria-hidden="true" size={16} />
              Refresh
            </Button>
          </div>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Marketplace" value={product.marketplace} />
          <Metric label="Currency" value={product.currency} />
          <Metric label="Target ACOS" value={product.target_acos} />
          <Metric label="Default bid" value={product.default_bid} />
          <Metric label="Default budget" value={product.default_budget} />
          <Metric label="ASIN" value={product.asin ?? "-"} />
          <Metric label="SKU" value={product.sku ?? "-"} />
          <Metric label="Status" value={product.status} />
        </dl>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <WorkflowCard
          href={`/products/${productId}/uploads`}
          icon={<UploadCloud aria-hidden="true" size={18} />}
          label="Upload research"
          meta={`${uploads.length} files`}
          status={uploads.length ? "Ready" : "Next step"}
        />
        <WorkflowCard
          href={latestProcessedUpload ? `/products/${productId}/uploads/${latestProcessedUpload.id}/mapping` : `/products/${productId}/uploads`}
          icon={<FileSpreadsheet aria-hidden="true" size={18} />}
          label="Map and score keywords"
          meta={latestProcessedUpload ? latestProcessedUpload.original_filename : "Needs processed upload"}
          status={latestProcessedUpload ? "Open" : "Waiting"}
        />
        <WorkflowCard
          href={`/products/${productId}/monitoring`}
          icon={<FileSpreadsheet aria-hidden="true" size={18} />}
          label="Monitor running ads"
          meta="Import SP Search Term reports"
          status={latestProcessedUpload ? "Ready" : "Needs processed upload"}
        />
        <WorkflowCard
          href={latestProcessedUpload ? `/products/${productId}/uploads/${latestProcessedUpload.id}/mapping` : `/products/${productId}/uploads`}
          icon={<CheckCircle2 aria-hidden="true" size={18} />}
          label="Campaign plan and export"
          meta="Approval-controlled bulk CSV"
          status={latestProcessedUpload ? "Available after keyword set" : "Waiting"}
        />
      </div>

      <div className="rounded-md border border-slate-200 bg-white p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-900">Upload status</p>
            <p className="mt-1 text-sm text-slate-600">Processed uploads can be opened for mapping, scoring, campaign generation, and export.</p>
          </div>
          <Link className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white" href={`/products/${productId}/uploads`}>
            Manage uploads
          </Link>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <Metric label="Processed" value={String(statusCounts.processed ?? 0)} />
          <Metric label="Processing" value={String(statusCounts.processing ?? 0)} />
          <Metric label="Queued" value={String(statusCounts.queued_for_processing ?? 0)} />
          <Metric label="Failed" value={String(statusCounts.failed ?? 0)} />
        </div>
      </div>
    </div>
  );
}

function WorkspaceInput({ onChange, value }: { onChange: (value: string) => void; value: string }) {
  return (
    <label className="space-y-1 text-sm font-medium text-slate-700">
      Workspace ID
      <input className="block w-72 rounded-md border border-slate-300 px-3 py-2 font-mono text-sm" onChange={(event) => onChange(event.target.value)} value={value} />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-sm font-semibold text-slate-950">{value}</dd>
    </div>
  );
}

function WorkflowCard({
  href,
  icon,
  label,
  meta,
  status,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  meta: string;
  status: string;
}) {
  return (
    <Link className="block rounded-md border border-slate-200 bg-white p-5 hover:border-slate-300 hover:bg-slate-50" href={href}>
      <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
        {icon}
        {label}
      </div>
      <p className="mt-3 text-lg font-semibold text-slate-950">{status}</p>
      <p className="mt-1 text-sm text-slate-600">{meta}</p>
    </Link>
  );
}
