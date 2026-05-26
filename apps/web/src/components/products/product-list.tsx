"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ProductProfile } from "@adsurf/types";
import { getProductProfiles } from "@/lib/api/products";

export function ProductList() {
  const [products, setProducts] = useState<ProductProfile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getProductProfiles()
      .then((loadedProducts) => {
        if (active) setProducts(loadedProducts);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "Product profiles could not be loaded.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (isLoading) {
    return <div className="p-8 text-sm text-slate-600">Loading product profiles...</div>;
  }

  if (error) {
    return <div className="p-8 text-sm text-red-700">{error}</div>;
  }

  if (products.length === 0) {
    return <div className="p-8 text-sm text-slate-600">No product profiles yet.</div>;
  }

  return (
    <ul className="divide-y divide-slate-200">
      {products.map((product) => (
        <li className="p-4" key={product.id}>
          <Link className="font-medium text-slate-950" href={`/products/${product.id}`}>
            {product.product_name}
          </Link>
          <p className="text-sm text-slate-500">
            {product.marketplace} / {product.currency}
          </p>
        </li>
      ))}
    </ul>
  );
}
