"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ChevronRight, PackageSearch, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { ProductProfile } from "@adsurf/types";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { bulkDeleteProductProfiles, deleteProductProfile, getProductProfiles } from "@/lib/api/products";
import { invalidateCache } from "@/lib/prefetch/prefetch-cache";
import { usePrefetchedData } from "@/lib/prefetch/use-prefetched-data";

export function ProductList() {
  const router = useRouter();
  const { data: products, isLoading, error, refetch } = usePrefetchedData<ProductProfile[]>(
    "products:list",
    () => getProductProfiles(),
    120_000,
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState<{ mode: "single"; id: string; name: string } | { mode: "bulk"; ids: string[] } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (isLoading && !products) {
    return <LoadingSpinner message="Loading product profiles" subtext="Fetching your workspace products" />;
  }

  if (error) {
    return <div className="p-8 text-sm text-red-700 dark:text-red-400">{error}</div>;
  }

  if (!products || products.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-400 dark:border-white/10 dark:bg-white/5">
          <PackageSearch size={20} />
        </div>
        <p className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-300">No product profiles yet</p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Create your first product profile to start managing Amazon Ads campaigns.</p>
      </div>
    );
  }

  const allSelected = products.length > 0 && selected.size === products.length;
  const someSelected = selected.size > 0 && !allSelected;

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(products!.map((p) => p.id)));
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function handleConfirmedDelete() {
    if (!confirmDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      if (confirmDelete.mode === "single") {
        await deleteProductProfile(confirmDelete.id);
      } else {
        await bulkDeleteProductProfiles(confirmDelete.ids);
      }
      setSelected(new Set());
      setConfirmDelete(null);
      invalidateCache("products:");
      await refetch();
      router.refresh();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <>
      {/* Bulk action toolbar */}
      {selected.size > 0 && (
        <div className="flex items-center justify-between border-b border-indigo-100 bg-indigo-50/80 px-5 py-2.5 dark:border-indigo-400/20 dark:bg-indigo-400/10">
          <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
            {selected.size} selected
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() =>
                setConfirmDelete({ mode: "bulk", ids: Array.from(selected) })
              }
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-600 transition hover:border-red-300 hover:bg-red-50 dark:border-red-400/30 dark:bg-transparent dark:text-red-400 dark:hover:bg-red-400/10"
            >
              <Trash2 size={13} />
              Delete {selected.size}
            </button>
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-white/10"
              aria-label="Clear selection"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      <ul className="divide-y divide-slate-100 dark:divide-white/10">
        {/* Select-all header row */}
        <li className="flex items-center gap-3 px-5 py-2">
          <input
            type="checkbox"
            aria-label="Select all products"
            checked={allSelected}
            ref={(el) => {
              if (el) el.indeterminate = someSelected;
            }}
            onChange={toggleAll}
            className="h-4 w-4 cursor-pointer rounded border-slate-300 text-indigo-600 transition focus:ring-indigo-500 dark:border-white/20 dark:bg-white/5"
          />
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {allSelected ? "Deselect all" : "Select all"}
          </span>
        </li>

        {products.map((product) => (
          <li key={product.id} className={`group flex items-center gap-3 px-5 py-0 transition-colors ${selected.has(product.id) ? "bg-indigo-50/60 dark:bg-indigo-400/[0.06]" : "hover:bg-slate-50/80 dark:hover:bg-white/[0.03]"}`}>
            {/* Checkbox */}
            <input
              type="checkbox"
              aria-label={`Select ${product.product_name}`}
              checked={selected.has(product.id)}
              onChange={() => toggleOne(product.id)}
              onClick={(e) => e.stopPropagation()}
              className="h-4 w-4 cursor-pointer rounded border-slate-300 text-indigo-600 transition focus:ring-indigo-500 dark:border-white/20 dark:bg-white/5"
            />

            {/* Main row link */}
            <Link
              href={`/products/${product.id}`}
              className="flex flex-1 items-center gap-4 py-4"
            >
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition ${selected.has(product.id) ? "border-indigo-200 bg-indigo-50 text-indigo-600 dark:border-indigo-400/30 dark:bg-indigo-300/10 dark:text-indigo-300" : "border-slate-200 bg-slate-50 text-slate-500 group-hover:border-indigo-200 group-hover:bg-indigo-50 group-hover:text-indigo-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 dark:group-hover:border-indigo-400/30 dark:group-hover:bg-indigo-300/10 dark:group-hover:text-indigo-300"}`}>
                <PackageSearch aria-hidden="true" size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-slate-950 transition group-hover:text-indigo-700 dark:text-white dark:group-hover:text-indigo-200">
                  {product.product_name}
                </p>
                <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
                  {product.marketplace} · {product.currency}
                </p>
              </div>
              <ChevronRight
                aria-hidden="true"
                size={16}
                className="shrink-0 text-slate-400 transition group-hover:text-indigo-500 dark:group-hover:text-indigo-300"
              />
            </Link>

            {/* Per-row delete button */}
            <button
              type="button"
              aria-label={`Delete ${product.product_name}`}
              onClick={(e) => {
                e.preventDefault();
                setConfirmDelete({ mode: "single", id: product.id, name: product.product_name });
              }}
              className="ml-1 rounded-lg p-1.5 text-slate-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 focus-visible:opacity-100 dark:hover:bg-red-400/10 dark:hover:text-red-400"
            >
              <Trash2 size={15} />
            </button>
          </li>
        ))}
      </ul>

      {/* Confirmation dialog */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm dark:bg-black/60"
            onClick={() => !isDeleting && setConfirmDelete(null)}
          />

          {/* Panel */}
          <div className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-100 text-red-600 dark:bg-red-400/15 dark:text-red-400">
                <AlertTriangle size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="delete-dialog-title" className="text-base font-semibold text-slate-900 dark:text-white">
                  {confirmDelete.mode === "single"
                    ? "Delete product profile?"
                    : `Delete ${confirmDelete.ids.length} product profiles?`}
                </h2>
                <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400">
                  {confirmDelete.mode === "single" ? (
                    <>
                      <span className="font-medium text-slate-800 dark:text-slate-200">{confirmDelete.name}</span> will be permanently deleted.
                      This cannot be undone.
                    </>
                  ) : (
                    <>
                      {confirmDelete.ids.length} product profiles will be permanently deleted.
                      This cannot be undone.
                    </>
                  )}
                </p>
                {deleteError && (
                  <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300">
                    {deleteError}
                  </p>
                )}
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setConfirmDelete(null);
                  setDeleteError(null);
                }}
                disabled={isDeleting}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmedDelete}
                disabled={isDeleting}
                className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-60 dark:bg-red-500 dark:hover:bg-red-600"
              >
                {isDeleting ? (
                  <>
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Deleting…
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
