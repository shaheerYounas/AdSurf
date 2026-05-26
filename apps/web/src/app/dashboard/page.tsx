import { PageHeader } from "@/components/page-header";
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
    <section className="space-y-6">
      <PageHeader
        eyebrow="Workspace command center"
        title="Dashboard"
        description="Track products, uploaded research files, parsing progress, and the launch checklist for approval-controlled bulk export."
      />
      <DashboardOverview initialSummary={initialSummary} />
    </section>
  );
}
