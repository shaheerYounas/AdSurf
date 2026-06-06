import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { ProductList } from "@/components/products/product-list";
import { BatchReportUpload } from "@/components/uploads/batch-report-upload";

export default function ProductsPage() {
  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          eyebrow="Workspace products"
          title="Products"
          description="Create and manage product profiles before uploads, keyword scoring, or campaign planning."
        />
        <Link className="inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-lg active:translate-y-0 bg-indigo-600 text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 min-h-10" href="/products/new">
          New product
        </Link>
      </div>
      <div className="rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-slate-950/70">
        <ProductList />
      </div>
      <div className="rounded-lg border border-violet-200 bg-white p-6 shadow-sm">
        <BatchReportUpload />
      </div>
    </section>
  );
}
