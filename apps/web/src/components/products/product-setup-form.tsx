"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createProductProfile } from "@/lib/api/products";

export function ProductSetupForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    const formData = new FormData(event.currentTarget);
    try {
      const product = await createProductProfile({
        product_name: String(formData.get("product_name") ?? ""),
        asin: normalizedOptional(formData.get("asin")),
        sku: normalizedOptional(formData.get("sku")),
        marketplace: String(formData.get("marketplace") ?? "US"),
        currency: String(formData.get("currency") ?? "USD"),
        target_acos: String(formData.get("target_acos") ?? "0.50"),
        default_budget: String(formData.get("default_budget") ?? "10.00"),
        default_bid: String(formData.get("default_bid") ?? "1.00"),
      });
      router.push(`/products/${product.id}`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Product profile could not be saved.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="grid gap-5 rounded-lg border border-slate-200 bg-white p-6 md:grid-cols-2" onSubmit={onSubmit}>
      <label className="space-y-2">
        <span className="text-sm font-medium">Product name</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" name="product_name" required />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">ASIN</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" maxLength={10} name="asin" />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">SKU</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" name="sku" />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">Marketplace</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" defaultValue="US" name="marketplace" />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">Currency</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" defaultValue="USD" name="currency" />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">Target ACOS</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" defaultValue="0.50" name="target_acos" type="number" step="0.01" min="0.01" max="1" />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">Default budget</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" defaultValue="10.00" name="default_budget" type="number" step="0.01" min="0.01" />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium">Default bid</span>
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" defaultValue="1.00" name="default_bid" type="number" step="0.01" min="0.01" />
      </label>
      <div className="md:col-span-2">
        {error ? <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        <button className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:bg-slate-300" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Saving" : "Save product"}
        </button>
      </div>
    </form>
  );
}

function normalizedOptional(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").trim();
  return normalized ? normalized : null;
}
