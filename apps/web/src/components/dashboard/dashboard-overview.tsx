"use client";

import Link from "next/link";
import { AlertCircle, Boxes, CheckCircle2, ChevronRight, Clock3, DatabaseZap, FileSpreadsheet, Loader2, RefreshCw, ShieldCheck, Sparkles, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { defaultWorkspaceId } from "@/lib/api/client";
import { getDashboardSummary, type DashboardSummary } from "@/lib/api/products";

export function DashboardOverview({ initialSummary = null }: { initialSummary?: DashboardSummary | null }) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [summary, setSummary] = useState<DashboardSummary | null>(initialSummary);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(!initialSummary);

  useEffect(() => {
    if (!initialSummary) {
      loadDashboard();
    }
  }, []);

  async function loadDashboard() {
    setError(null);
    setIsRefreshing(true);
    try {
      const loadedSummary = await getDashboardSummary(workspaceId);
      setSummary(loadedSummary);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Dashboard could not be loaded.");
    } finally {
      setIsRefreshing(false);
    }
  }

  const products = summary?.products ?? [];
  const uploadCounts = summary?.upload_counts ?? {};
  const recommendations = summary?.top_recommendations ?? [];
  const isSyncingInitialData = isRefreshing && !summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <label className="space-y-1 text-sm font-medium text-slate-700">
          Workspace ID
          <input
            className="block w-72 rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
            id="dashboard-workspace-id"
            name="workspace_id"
            onChange={(event) => setWorkspaceId(event.target.value)}
            value={workspaceId}
          />
        </label>
        <Button className="inline-flex items-center gap-2 bg-slate-700" disabled={isRefreshing} onClick={loadDashboard} type="button">
          {isRefreshing ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <RefreshCw aria-hidden="true" size={16} />}
          Refresh
        </Button>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <AlertCircle aria-hidden="true" size={18} />
          {error}
        </div>
      ) : null}

      {isSyncingInitialData ? (
        <div className="flex items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
          <Loader2 aria-hidden="true" className="animate-spin" size={18} />
          Supabase is still syncing dashboard data. You can continue using the app while the numbers refresh.
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <DashboardCard icon={<Boxes aria-hidden="true" size={18} />} label="Products" value={summary?.product_count ?? 0} />
        <DashboardCard icon={<UploadCloud aria-hidden="true" size={18} />} label="Uploads" value={summary?.upload_count ?? 0} />
        <DashboardCard icon={<CheckCircle2 aria-hidden="true" size={18} />} label="Processed uploads" value={uploadCounts.processed ?? 0} />
        <DashboardCard icon={<Clock3 aria-hidden="true" size={18} />} label="Pending recommendations" value={summary?.pending_recommendation_count ?? 0} />
      </div>

      <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        <div className="flex items-center gap-2 font-medium">
          <ShieldCheck aria-hidden="true" size={18} />
          Recommendation only
        </div>
        <p className="mt-1">Dashboard recommendations require human approval and do not change Amazon Ads accounts.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-md border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <FileSpreadsheet aria-hidden="true" className="text-slate-500" size={18} />
            <p className="text-sm font-medium text-slate-900">Products ready for workflow</p>
          </div>
          {products.length ? (
            <ul className="divide-y divide-slate-200">
              {products.map((product) => (
                <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={product.id}>
                  <div>
                    <Link className="font-medium text-slate-950" href={`/products/${product.id}`}>
                      {product.product_name}
                    </Link>
                    <p className="text-sm text-slate-500">
                      {product.marketplace} / {product.currency} / target ACOS {product.target_acos}
                    </p>
                  </div>
                  <Link className="inline-flex items-center gap-1 rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white" href={`/products/${product.id}/uploads`}>
                    Continue
                    <ChevronRight aria-hidden="true" size={16} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : isSyncingInitialData ? (
            <div className="flex items-center gap-2 px-5 py-8 text-sm text-slate-600">
              <Loader2 aria-hidden="true" className="animate-spin" size={16} />
              Loading product workflow data...
            </div>
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

        <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Sparkles aria-hidden="true" className="text-slate-500" size={18} />
            <p className="text-sm font-medium text-slate-900">Launch checklist</p>
          </div>
          <div className="mt-4 space-y-3">
            <ChecklistItem done={(summary?.product_count ?? 0) > 0} label="Create product profile" />
            <ChecklistItem done={(summary?.upload_count ?? 0) > 0} label="Upload research file" />
            <ChecklistItem done={(uploadCounts.processed ?? 0) > 0} label="Process upload rows" />
            <ChecklistItem done={false} label="Approve mapping and keyword set" />
            <ChecklistItem done={false} label="Approve campaign plan and export" />
            <ChecklistItem done={recommendations.length > 0} label="Generate rule recommendations" />
          </div>
        </section>
      </div>

      <section className="rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
          <DatabaseZap aria-hidden="true" className="text-slate-500" size={18} />
          <p className="text-sm font-medium text-slate-900">Rule recommendation queue</p>
        </div>
        {recommendations.length ? (
          <ul className="divide-y divide-slate-200">
            {recommendations.map((recommendation) => (
              <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={recommendation.id}>
                <div>
                  <p className="font-medium text-slate-950">{recommendation.recommendation_type} / {recommendation.priority}</p>
                  <p className="text-sm text-slate-600">{recommendation.campaign_name} / {recommendation.customer_search_term}</p>
                  <p className="mt-1 text-xs text-slate-500">Requires human approval. Does not change Amazon Ads account.</p>
                </div>
                <Link className="inline-flex items-center gap-1 rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white" href="/recommendations">
                  Review
                  <ChevronRight aria-hidden="true" size={16} />
                </Link>
              </li>
            ))}
          </ul>
        ) : isSyncingInitialData ? (
          <div className="flex items-center gap-2 px-5 py-8 text-sm text-slate-600">
            <Loader2 aria-hidden="true" className="animate-spin" size={16} />
            Loading recommendation queue...
          </div>
        ) : (
          <p className="px-5 py-8 text-sm text-slate-600">No rule recommendations yet. Import a performance report from a product monitoring page.</p>
        )}
      </section>
    </div>
  );
}

function DashboardCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
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
