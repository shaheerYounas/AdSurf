import { DashboardOverview } from "@/components/dashboard/dashboard-overview";
import { defaultWorkspaceId } from "@/lib/api/client";
import { getDashboardSummary, type DashboardSummary } from "@/lib/api/products";

async function loadInitialDashboardSummary(): Promise<DashboardSummary | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2500);

  try {
    return await getDashboardSummary(defaultWorkspaceId, { signal: controller.signal });
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export default async function DashboardPage() {
  const initialSummary = await loadInitialDashboardSummary();

  return (
    <section className="rounded-[1.75rem] bg-slate-100 p-3 text-slate-950 dark:bg-slate-950 dark:text-white sm:p-4 lg:p-5">
      <header className="rounded-3xl border border-white/10 bg-[linear-gradient(135deg,#020617,#111827_48%,#172554)] p-6 shadow-xl shadow-slate-950/20 sm:p-8">
        <p className="inline-flex rounded-full border border-indigo-300/25 bg-indigo-300/10 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.22em] text-indigo-100">
          Workspace command center
        </p>
        <h1 className="heading-fluid-lg mt-4 font-semibold tracking-tight text-white">Dashboard</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
          Track products, uploaded research files, parsing progress, and the launch checklist for approval-controlled bulk export.
        </p>
      </header>
      <DashboardOverview initialSummary={initialSummary} />
    </section>
  );
}
