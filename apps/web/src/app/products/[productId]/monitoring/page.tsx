import { PageHeader } from "@/components/page-header";
import { MonitoringWorkspace } from "@/components/monitoring/monitoring-workspace";

type ProductMonitoringPageProps = {
  params: Promise<{ productId: string }>;
};

export default async function ProductMonitoringPage({ params }: ProductMonitoringPageProps) {
  const { productId } = await params;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Agent monitoring"
        title="Performance report to recommendations"
        description="Import Sponsored Products Search Term reports, let rules generate recommendations, and review agent explanations before approval."
      />
      <MonitoringWorkspace productId={productId} />
    </section>
  );
}
