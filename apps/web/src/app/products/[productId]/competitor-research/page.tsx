import { CompetitorResearchWorkspace } from "@/components/products/competitor-research-workspace";

interface Props {
  params: Promise<{ productId: string }>;
}

export async function generateMetadata({ params }: Props) {
  const { productId } = await params;
  return {
    title: `Competitor research | AdSurf`,
    description: `Run live Amazon competitor research for product ${productId}.`,
  };
}

export default async function CompetitorResearchPage({ params }: Props) {
  const { productId } = await params;
  return <CompetitorResearchWorkspace productId={productId} />;
}
