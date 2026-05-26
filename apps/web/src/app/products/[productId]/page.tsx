import { PageHeader } from "@/components/page-header";
import { ProductDetailPanel } from "@/components/products/product-detail-panel";

type ProductDetailPageProps = {
  params: Promise<{ productId: string }>;
};

export default async function ProductDetailPage({ params }: ProductDetailPageProps) {
  const { productId } = await params;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Product detail"
        title="Product profile"
        description="Review product defaults, upload status, and the next action in the approval-controlled campaign workflow."
      />
      <ProductDetailPanel productId={productId} />
    </section>
  );
}
