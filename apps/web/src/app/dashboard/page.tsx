import { PageHeader } from "@/components/page-header";
import { DashboardOverview } from "@/components/dashboard/dashboard-overview";

export default function DashboardPage() {
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Workspace command center"
        title="Dashboard"
        description="Track products, uploaded research files, parsing progress, and the launch checklist for approval-controlled bulk export."
      />
      <DashboardOverview />
    </section>
  );
}
