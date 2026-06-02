import { CompetitorWorkflow } from "@/components/competitor/competitor-workflow";
import { PageHeader } from "@/components/page-header";

type ProductCompetitorsPageProps = {
  params: Promise<{ productId: string }>;
};

export default async function ProductCompetitorsPage({ params }: ProductCompetitorsPageProps) {
  const { productId } = await params;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Competitor research"
        title="Verified keyword launch plan"
        description="Clean, score, verify with Amazon result evidence, and prepare approval-controlled Sponsored Products campaign rows."
      />
      <CompetitorWorkflow productId={productId} />
    </section>
  );
}
