"use client";

import Link from "next/link";
import type { ProductProfile } from "@adsurf/types";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { getProductProfiles } from "@/lib/api/products";
import { usePrefetchedData } from "@/lib/prefetch/use-prefetched-data";

export function ProductList() {
  const { data: products, isLoading, error } = usePrefetchedData<ProductProfile[]>(
    "products:list",
    () => getProductProfiles(),
    120_000,
  );

  if (isLoading && !products) {
    return <LoadingSpinner message="Loading product profiles" subtext="Fetching your workspace products" />;
  }

  if (error) {
    return <div className="p-8 text-sm text-red-700 dark:text-red-400">{error}</div>;
  }

  if (!products || products.length === 0) {
    return <div className="p-8 text-sm text-slate-600 dark:text-slate-400">No product profiles yet.</div>;
  }

  return (
    <ul className="divide-y divide-slate-200 dark:divide-white/10">
      {products.map((product) => (
        <li className="p-4 transition-colors hover:bg-slate-50 dark:hover:bg-white/5" key={product.id}>
          <Link className="font-medium text-slate-950 dark:text-white" href={`/products/${product.id}`}>
            {product.product_name}
          </Link>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {product.marketplace} / {product.currency}
          </p>
        </li>
      ))}
    </ul>
  );
}