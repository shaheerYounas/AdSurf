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
    <div className="mt-6 space-y-6">
      <section className="rounded-3xl border border-white/10 bg-slate-950/90 p-5 shadow-xl shadow-slate-950/20 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <label className="block text-sm font-semibold text-slate-200">
            Workspace ID
            <input
              className="mt-2 block min-h-11 w-full min-w-0 rounded-2xl border border-white/10 bg-slate-900 px-3 py-2 font-mono text-sm text-white outline-none focus:ring-2 focus:ring-indigo-300 sm:w-80"
              id="dashboard-workspace-id"
              name="workspace_id"
              onChange={(event) => setWorkspaceId(event.target.value)}
              value={workspaceId}
            />
          </label>
          <Button disabled={isRefreshing} onClick={loadDashboard} type="button" variant="primary">
            {isRefreshing ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <RefreshCw aria-hidden="true" size={16} />}
            Refresh
          </Button>
        </div>
      </section>

      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-red-300/30 bg-red-400/10 px-4 py-3 text-sm font-semibold text-red-100">
          <AlertCircle aria-hidden="true" size={18} />
          {error}
        </div>
      ) : null}

      {isSyncingInitialData ? (
        <div className="flex items-center gap-2 rounded-2xl border border-sky-300/25 bg-sky-300/10 px-4 py-3 text-sm font-semibold text-sky-100">
          <Loader2 aria-hidden="true" className="animate-spin" size={18} />
          Supabase is still syncing dashboard data. You can continue using the app while the numbers refresh.
        </div>
      ) : null}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        <DashboardCard icon={<Boxes aria-hidden="true" size={18} />} label="Products" value={summary?.product_count ?? 0} />
        <DashboardCard icon={<UploadCloud aria-hidden="true" size={18} />} label="Uploads" value={summary?.upload_count ?? 0} />
        <DashboardCard icon={<CheckCircle2 aria-hidden="true" size={18} />} label="Processed uploads" value={uploadCounts.processed ?? 0} />
        <DashboardCard icon={<Clock3 aria-hidden="true" size={18} />} label="Pending recommendations" value={summary?.pending_recommendation_count ?? 0} />
      </div>

      <div className="rounded-3xl border border-emerald-300/25 bg-emerald-300/10 px-5 py-4 text-sm text-emerald-100 shadow-sm">
        <div className="flex flex-wrap gap-2">
          <SafetyPill text="Recommendation only" />
          <SafetyPill text="Requires human approval" />
          <SafetyPill text="No live Amazon Ads change executed" />
        </div>
        <p className="mt-3 leading-6 text-emerald-50">Dashboard recommendations require human approval and do not change Amazon Ads accounts.</p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="overflow-hidden rounded-3xl border border-white/10 bg-slate-950/90 shadow-xl shadow-slate-950/20">
          <SectionHeader icon={<FileSpreadsheet aria-hidden="true" size={18} />} title="Products ready for workflow" />
          {products.length ? (
            <ul className="divide-y divide-white/10">
              {products.map((product) => (
                <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={product.id}>
                  <div className="min-w-0">
                    <Link className="font-semibold text-white hover:text-indigo-200" href={`/products/${product.id}`}>
                      {product.product_name}
                    </Link>
                    <p className="mt-1 text-sm leading-6 text-slate-400">
                      {product.marketplace} / {product.currency} / target ACOS {product.target_acos}
                    </p>
                  </div>
                  <Link className="inline-flex min-h-10 items-center gap-1 rounded-full bg-indigo-300 px-4 text-sm font-semibold text-indigo-950 hover:bg-indigo-200" href={`/products/${product.id}/uploads`}>
                    Continue
                    <ChevronRight aria-hidden="true" size={16} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : isSyncingInitialData ? (
            <EmptyState icon={<Loader2 aria-hidden="true" className="animate-spin" size={16} />} message="Loading product workflow data..." />
          ) : (
            <div className="px-5 py-8 text-sm leading-6 text-slate-300">
              No products yet.{" "}
              <Link className="font-semibold text-indigo-200 underline" href="/products/new">
                Create the first product
              </Link>
              .
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-white/10 bg-slate-950/90 p-5 shadow-xl shadow-slate-950/20">
          <div className="flex items-center gap-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-indigo-300 text-indigo-950">
              <Sparkles aria-hidden="true" size={18} />
            </span>
            <p className="text-base font-semibold text-white">Launch checklist</p>
          </div>
          <div className="mt-5 space-y-3">
            <ChecklistItem done={(summary?.product_count ?? 0) > 0} label="Create product profile" />
            <ChecklistItem done={(summary?.upload_count ?? 0) > 0} label="Upload research file" />
            <ChecklistItem done={(uploadCounts.processed ?? 0) > 0} label="Process upload rows" />
            <ChecklistItem done={false} label="Approve mapping and keyword set" />
            <ChecklistItem done={false} label="Approve campaign plan and export" />
            <ChecklistItem done={recommendations.length > 0} label="Generate rule recommendations" />
          </div>
        </section>
      </div>

      <section className="overflow-hidden rounded-3xl border border-white/10 bg-slate-950/90 shadow-xl shadow-slate-950/20">
        <SectionHeader icon={<DatabaseZap aria-hidden="true" size={18} />} title="Rule recommendation queue" />
        {recommendations.length ? (
          <ul className="divide-y divide-white/10">
            {recommendations.map((recommendation) => (
              <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={recommendation.id}>
                <div className="min-w-0">
                  <p className="font-semibold text-white">{recommendation.recommendation_type} / {recommendation.priority}</p>
                  <p className="mt-1 text-sm text-slate-300">{recommendation.campaign_name} / {recommendation.customer_search_term}</p>
                  <p className="mt-1 text-xs font-semibold text-emerald-200">Requires human approval. Does not change Amazon Ads account.</p>
                </div>
                <Link className="inline-flex min-h-10 items-center gap-1 rounded-full bg-indigo-300 px-4 text-sm font-semibold text-indigo-950 hover:bg-indigo-200" href="/recommendations">
                  Review
                  <ChevronRight aria-hidden="true" size={16} />
                </Link>
              </li>
            ))}
          </ul>
        ) : isSyncingInitialData ? (
          <EmptyState icon={<Loader2 aria-hidden="true" className="animate-spin" size={16} />} message="Loading recommendation queue..." />
        ) : (
          <p className="px-5 py-8 text-sm leading-6 text-slate-300">No rule recommendations yet. Import a performance report from a product monitoring page.</p>
        )}
      </section>
    </div>
  );
}

function DashboardCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/90 p-5 shadow-xl shadow-slate-950/20">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-300">
        <span className="flex h-9 w-9 items-center justify-center rounded-2xl bg-white/10 text-indigo-200">{icon}</span>
        {label}
      </div>
      <p className="mt-4 text-3xl font-semibold text-white">{value}</p>
    </div>
  );
}

function SectionHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 border-b border-white/10 px-5 py-4">
      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/10 text-indigo-200">{icon}</span>
      <p className="text-base font-semibold text-white">{title}</p>
    </div>
  );
}

function EmptyState({ icon, message }: { icon: ReactNode; message: string }) {
  return (
    <div className="flex items-center gap-2 px-5 py-8 text-sm text-slate-300">
      {icon}
      {message}
    </div>
  );
}

function SafetyPill({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 text-xs font-semibold text-emerald-100">
      <ShieldCheck size={14} /> {text}
    </span>
  );
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm">
      <span className={done ? "text-emerald-300" : "text-slate-500"}>
        <CheckCircle2 aria-hidden="true" size={18} />
      </span>
      <span className={done ? "font-semibold text-white" : "text-slate-300"}>{label}</span>
    </div>
  );
}
