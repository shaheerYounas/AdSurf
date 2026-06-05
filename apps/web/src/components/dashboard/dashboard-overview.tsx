"use client";

import Link from "next/link";
import { Boxes, CheckCircle2, ChevronRight, Clock3, DatabaseZap, FileSpreadsheet, Loader2, RefreshCw, ShieldCheck, Sparkles, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { getDashboardSummary, type DashboardSummary } from "@/lib/api/products";
import { getCachedData, setCachedData } from "@/lib/prefetch";

export function DashboardOverview({ initialSummary = null }: { initialSummary?: DashboardSummary | null }) {
  const [workspaceId] = useState(defaultWorkspaceId);
  const [summary, setSummary] = useState<DashboardSummary | null>(initialSummary);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(!initialSummary);

  useEffect(() => {
    if (!initialSummary) {
      loadDashboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadDashboard() {
    setError(null);

    // Data may already be prefetched in background.
    const cached = getCachedData<DashboardSummary>("dashboard:summary");
    if (cached) {
      setSummary(cached);
      setIsRefreshing(false);
      return;
    }

    setIsRefreshing(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);
    try {
      const loadedSummary = await getDashboardSummary(workspaceId, { signal: controller.signal });
      setCachedData("dashboard:summary", loadedSummary, 120_000);
      setSummary(loadedSummary);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError("The dashboard request timed out. The database may be under load — please try refreshing.");
      } else {
        setError(formatApiError(caught, "Dashboard could not be loaded."));
      }
    } finally {
      clearTimeout(timeout);
      setIsRefreshing(false);
    }
  }

  const products = summary?.products ?? [];
  const uploadCounts = summary?.upload_counts ?? {};
  const recommendations = summary?.top_recommendations ?? [];
  const isSyncingInitialData = isRefreshing && !summary;

  return (
    <div className="mt-8 space-y-8">
      {/* Inline workspace + refresh — subtle, collapsed into one row */}
      <div className="flex flex-wrap items-center justify-end gap-3">
        <span className="hidden text-xs font-medium text-slate-400 dark:text-slate-500 sm:inline">Workspace: {workspaceId}</span>
        <Button disabled={isRefreshing} onClick={loadDashboard} size="sm" type="button" variant="secondary">
          {isRefreshing ? <Loader2 aria-hidden="true" className="animate-spin" size={14} /> : <RefreshCw aria-hidden="true" size={14} />}
          Refresh
        </Button>
      </div>

      {error ? (
        <ErrorNotice
          actionLabel="Refresh dashboard"
          message={error}
          onAction={loadDashboard}
          title="Dashboard data could not be refreshed"
        />
      ) : null}

      {isSyncingInitialData ? (
        <div className="flex items-center gap-2 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm font-semibold text-sky-950 shadow-sm dark:border-sky-300/25 dark:bg-sky-300/10 dark:text-sky-100" role="status" aria-live="polite">
          <Loader2 aria-hidden="true" className="animate-spin" size={18} />
          Gathering your workspace data. Feel free to explore — numbers will appear shortly.
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 shadow-sm dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-100">
        <ShieldCheck aria-hidden="true" size={18} />
        <span className="font-semibold">Recommendation only</span>
        <span className="text-emerald-700 dark:text-emerald-200">Does not change Amazon Ads account without approval.</span>
      </div>

      {/* Metric cards — lighter, more spacious */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-5">
        <DashboardCard icon={<Boxes aria-hidden="true" size={18} />} label="Products" value={summary?.product_count ?? 0} tone="indigo" />
        <DashboardCard icon={<UploadCloud aria-hidden="true" size={18} />} label="Uploads" value={summary?.upload_count ?? 0} tone="sky" />
        <DashboardCard icon={<CheckCircle2 aria-hidden="true" size={18} />} label="Processed uploads" value={uploadCounts.processed ?? 0} tone="emerald" />
        <DashboardCard icon={<Clock3 aria-hidden="true" size={18} />} label="Pending recommendations" value={summary?.pending_recommendation_count ?? 0} tone="amber" />
      </div>

      {/* Two-column: products + checklist */}
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/90">
          <SectionHeader icon={<FileSpreadsheet aria-hidden="true" size={16} />} title="Products ready for workflow" />
          {products.length ? (
            <ul className="divide-y divide-slate-100 dark:divide-white/10">
              {products.map((product) => (
                <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={product.id}>
                  <div className="min-w-0">
                    <Link className="font-semibold text-slate-950 hover:text-indigo-600 dark:text-white dark:hover:text-indigo-200" href={`/products/${product.id}`}>
                      {product.product_name}
                    </Link>
                    <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
                      {product.marketplace} / {product.currency} / target ACOS {product.target_acos}
                    </p>
                  </div>
                  <Link className="inline-flex min-h-9 items-center gap-1 rounded-full bg-indigo-100 px-4 text-sm font-semibold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-300/15 dark:text-indigo-100 dark:hover:bg-indigo-300/25" href={`/products/${product.id}/uploads`}>
                    Continue
                    <ChevronRight aria-hidden="true" size={14} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : isSyncingInitialData ? (
            <EmptyState icon={<Loader2 aria-hidden="true" className="animate-spin" size={16} />} message="Loading product workflow data..." />
          ) : (
            <div className="px-5 py-8 text-sm leading-6 text-slate-500 dark:text-slate-300">
              No products yet.{" "}
              <Link className="font-semibold text-indigo-600 underline dark:text-indigo-200" href="/products/new">
                Create the first product
              </Link>
              .
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/90">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700 dark:bg-indigo-500/30 dark:text-indigo-300">
              <Sparkles aria-hidden="true" size={16} />
            </span>
            <p className="text-base font-semibold text-slate-950 dark:text-white">Launch checklist</p>
          </div>
          <div className="mt-5 space-y-2.5">
            <ChecklistItem done={(summary?.product_count ?? 0) > 0} label="Create product profile" />
            <ChecklistItem done={(summary?.upload_count ?? 0) > 0} label="Upload research file" />
            <ChecklistItem done={(uploadCounts.processed ?? 0) > 0} label="Process upload rows" />
            <ChecklistItem done={false} label="Approve mapping and keyword set" />
            <ChecklistItem done={false} label="Approve campaign plan and export" />
            <ChecklistItem done={recommendations.length > 0} label="Generate rule recommendations" />
          </div>
        </section>
      </div>

      {/* Recommendation queue — summary with link instead of inline cards */}
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/90">
        <SectionHeader icon={<DatabaseZap aria-hidden="true" size={16} />} title="Rule recommendation queue" />
        {recommendations.length ? (
          <>
            <ul className="divide-y divide-slate-100 dark:divide-white/10">
              {recommendations.map((recommendation) => (
                <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={recommendation.id}>
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-950 dark:text-white">{recommendation.recommendation_type} / {recommendation.priority}</p>
                    <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-300">{recommendation.campaign_name} / {recommendation.customer_search_term}</p>
                  </div>
                  <Link className="inline-flex min-h-9 items-center gap-1 rounded-full bg-indigo-100 px-4 text-sm font-semibold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-300/15 dark:text-indigo-100 dark:hover:bg-indigo-300/25" href="/recommendations">
                    Review
                    <ChevronRight aria-hidden="true" size={14} />
                  </Link>
                </li>
              ))}
            </ul>
            <div className="border-t border-slate-100 px-5 py-3 dark:border-white/10">
              <Link className="text-sm font-semibold text-indigo-600 hover:text-indigo-500 dark:text-indigo-200 dark:hover:text-indigo-100" href="/recommendations">
                View all recommendations →
              </Link>
            </div>
          </>
        ) : isSyncingInitialData ? (
          <EmptyState icon={<Loader2 aria-hidden="true" className="animate-spin" size={16} />} message="Loading recommendation queue..." />
        ) : (
          <p className="px-5 py-8 text-sm leading-6 text-slate-500 dark:text-slate-300">No rule recommendations yet. Import a performance report from a product monitoring page.</p>
        )}
      </section>
    </div>
  );
}

type Tone = "indigo" | "sky" | "emerald" | "amber";

const toneStyles: Record<Tone, { icon: string; stat: string }> = {
  indigo: {
    icon: "bg-indigo-50 text-indigo-600 dark:bg-indigo-300/15 dark:text-indigo-300",
    stat: "text-indigo-600 dark:text-indigo-300",
  },
  sky: {
    icon: "bg-sky-50 text-sky-600 dark:bg-sky-300/15 dark:text-sky-300",
    stat: "text-sky-600 dark:text-sky-300",
  },
  emerald: {
    icon: "bg-emerald-50 text-emerald-600 dark:bg-emerald-300/15 dark:text-emerald-300",
    stat: "text-emerald-600 dark:text-emerald-300",
  },
  amber: {
    icon: "bg-amber-50 text-amber-600 dark:bg-amber-300/15 dark:text-amber-300",
    stat: "text-amber-600 dark:text-amber-300",
  },
};

function DashboardCard({ icon, label, value, tone = "indigo" }: { icon: ReactNode; label: string; value: number; tone?: Tone }) {
  const t = toneStyles[tone];
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/90">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${t.icon}`}>{icon}</span>
        {label}
      </div>
      <p className={`tabular-data mt-3 text-2xl font-semibold ${t.stat}`}>{value}</p>
    </div>
  );
}

function SectionHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-3.5 dark:border-white/10">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-indigo-600 dark:bg-white/10 dark:text-indigo-200">{icon}</span>
      <p className="text-sm font-semibold text-slate-950 dark:text-white">{title}</p>
    </div>
  );
}

function EmptyState({ icon, message }: { icon: ReactNode; message: string }) {
  return (
    <div className="flex items-center gap-2 px-5 py-8 text-sm text-slate-500 dark:text-slate-300">
      {icon}
      {message}
    </div>
  );
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm dark:border-white/10 dark:bg-white/5">
      <span className={done ? "text-emerald-600 dark:text-emerald-300" : "text-slate-400 dark:text-slate-500"}>
        <CheckCircle2 aria-hidden="true" size={16} />
      </span>
      <span className={done ? "font-semibold text-slate-950 dark:text-white" : "text-slate-500 dark:text-slate-300"}>{label}</span>
    </div>
  );
}
