import { PageHeader } from "@/components/page-header";
import { ProductSetupForm } from "@/components/products/product-setup-form";

export default function NewProductPage() {
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Product setup"
        title="New product"
        description="Batch 1 provides the form shell only. Persistence is handled by the backend product profile API."
      />
      <ProductSetupForm />
    </section>
  );
}

