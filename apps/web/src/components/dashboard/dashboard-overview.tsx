"use client";

import Link from "next/link";
import { AlertCircle, Boxes, CheckCircle2, Clock3, RefreshCw, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { defaultWorkspaceId } from "@/lib/api/client";
import { getProductProfiles } from "@/lib/api/products";
import { getUploads, type UploadRecord } from "@/lib/api/uploads";
import { getRecommendations, type Recommendation } from "@/lib/api/monitoring";
import type { ProductProfile } from "@adsurf/types";

export function DashboardOverview() {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [products, setProducts] = useState<ProductProfile[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  const uploadCounts = useMemo(() => {
    return uploads.reduce<Record<string, number>>((counts, upload) => {
      counts[upload.status] = (counts[upload.status] ?? 0) + 1;
      return counts;
    }, {});
  }, [uploads]);

  async function loadDashboard() {
    setError(null);
    setIsLoading(true);
    try {
      const [loadedProducts, loadedUploads, loadedRecommendations] = await Promise.all([
        getProductProfiles(workspaceId),
        getUploads({ workspaceId }),
        getRecommendations(workspaceId),
      ]);
      setProducts(loadedProducts);
      setUploads(loadedUploads);
      setRecommendations(loadedRecommendations);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Dashboard could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  if (isLoading) {
    return <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-600">Loading workspace dashboard...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-md border border-slate-200 bg-white p-5">
        <label className="space-y-1 text-sm font-medium text-slate-700">
          Workspace ID
          <input className="block w-72 rounded-md border border-slate-300 px-3 py-2 font-mono text-sm" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
        </label>
        <Button className="inline-flex items-center gap-2 bg-slate-700" onClick={loadDashboard} type="button">
          <RefreshCw aria-hidden="true" size={16} />
          Refresh
        </Button>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <AlertCircle aria-hidden="true" size={18} />
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <DashboardCard icon={<Boxes aria-hidden="true" size={18} />} label="Products" value={products.length} />
        <DashboardCard icon={<UploadCloud aria-hidden="true" size={18} />} label="Uploads" value={uploads.length} />
        <DashboardCard icon={<CheckCircle2 aria-hidden="true" size={18} />} label="Processed uploads" value={uploadCounts.processed ?? 0} />
        <DashboardCard icon={<Clock3 aria-hidden="true" size={18} />} label="Pending recommendations" value={recommendations.filter((item) => item.status === "pending_approval").length} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-md border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4">
            <p className="text-sm font-medium text-slate-900">Products ready for workflow</p>
          </div>
          {products.length ? (
            <ul className="divide-y divide-slate-200">
              {products.slice(0, 6).map((product) => (
                <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={product.id}>
                  <div>
                    <Link className="font-medium text-slate-950" href={`/products/${product.id}`}>
                      {product.product_name}
                    </Link>
                    <p className="text-sm text-slate-500">
                      {product.marketplace} / {product.currency} / target ACOS {product.target_acos}
                    </p>
                  </div>
                  <Link className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white" href={`/products/${product.id}/uploads`}>
                    Continue
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-5 py-8 text-sm text-slate-600">
              No products yet.{" "}
              <Link className="font-medium text-slate-950 underline" href="/products/new">
                Create the first product
              </Link>
              .
            </div>
          )}
        </section>

        <section className="rounded-md border border-slate-200 bg-white p-5">
          <p className="text-sm font-medium text-slate-900">Launch checklist</p>
          <div className="mt-4 space-y-3">
            <ChecklistItem done={products.length > 0} label="Create product profile" />
            <ChecklistItem done={uploads.length > 0} label="Upload research file" />
            <ChecklistItem done={(uploadCounts.processed ?? 0) > 0} label="Process upload rows" />
            <ChecklistItem done={false} label="Approve mapping and keyword set" />
            <ChecklistItem done={false} label="Approve campaign plan and export" />
            <ChecklistItem done={recommendations.length > 0} label="Generate agent recommendations" />
          </div>
        </section>
      </div>

      <section className="rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4">
          <p className="text-sm font-medium text-slate-900">Agent recommendation queue</p>
        </div>
        {recommendations.length ? (
          <ul className="divide-y divide-slate-200">
            {recommendations.slice(0, 5).map((recommendation) => (
              <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={recommendation.id}>
                <div>
                  <p className="font-medium text-slate-950">{recommendation.recommendation_type} / {recommendation.priority}</p>
                  <p className="text-sm text-slate-600">{recommendation.campaign_name} / {recommendation.customer_search_term}</p>
                </div>
                <Link className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white" href="/recommendations">
                  Review
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 py-8 text-sm text-slate-600">No agent recommendations yet. Import a performance report from a product monitoring page.</p>
        )}
      </section>
    </div>
  );
}

function DashboardCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-2 text-sm text-slate-600">
        {icon}
        {label}
      </div>
      <p className="mt-3 text-3xl font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={done ? "text-emerald-700" : "text-slate-400"}>
        <CheckCircle2 aria-hidden="true" size={18} />
      </span>
      <span className={done ? "font-medium text-slate-900" : "text-slate-600"}>{label}</span>
    </div>
  );
}
