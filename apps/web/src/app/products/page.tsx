import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { ProductList } from "@/components/products/product-list";

export default function ProductsPage() {
  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          eyebrow="Workspace products"
          title="Products"
          description="Create and manage product profiles before uploads, keyword scoring, or campaign planning."
        />
        <Link className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white" href="/products/new">
          New product
        </Link>
      </div>
      <div className="rounded-lg border border-slate-200 bg-white">
        <ProductList />
      </div>
    </section>
  );
}
