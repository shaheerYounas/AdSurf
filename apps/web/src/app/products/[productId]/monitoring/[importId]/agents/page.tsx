import { PageHeader } from "@/components/page-header";
import { AgentControlCenter } from "@/components/agents/agent-control-center";

type ProductImportAgentsPageProps = {
  params: Promise<{ productId: string; importId: string }>;
};

export default async function ProductImportAgentsPage({ params }: ProductImportAgentsPageProps) {
  const { productId, importId } = await params;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Import workflow"
        title="Agent Control Center"
        description="Review this monitoring import's agent graph, event timeline, inputs, outputs, controls, and recommendation links."
      />
      <AgentControlCenter importId={importId} productId={productId} />
    </div>
  );
}
