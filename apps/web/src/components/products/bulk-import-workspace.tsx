"use client";

/**
 * Bulk product import workspace.
 *
 * 5-step flow:
 *  1. Upload — drag-and-drop or click to select CSV/XLSX
 *  2. Column preview — show detected column mapping
 *  3. Validation summary — totals, ready/invalid/duplicate breakdown
 *  4. Review exceptions — table of invalid/duplicate rows with error details
 *  5. Create results — confirmed creation with product count
 *
 * Products are NOT created until the user explicitly clicks "Create products"
 * in step 4. Steps 1–4 are entirely non-destructive.
 */

import Link from "next/link";
import { useState, useCallback, useRef } from "react";
import {
  uploadBulkProductFile,
  commitBulkProductImport,
  type BulkProductImportSummary,
  type BulkProductRow,
  type BulkImportConflictStrategy,
  type BulkImportCommitResult,
} from "@/lib/api/products";
import { formatApiError } from "@/lib/api/client";

// ─── Types ─────────────────────────────────────────────────────────────────────

type Step = 1 | 2 | 3 | 4 | 5;

// ─── Helpers ───────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const classes: Record<string, string> = {
    valid: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
    invalid: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
    duplicate_in_file: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
    already_exists: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
    skipped: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
    created: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
    updated: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300",
    failed: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
  };
  const labels: Record<string, string> = {
    valid: "Valid",
    invalid: "Invalid",
    duplicate_in_file: "Duplicate in file",
    already_exists: "Already exists",
    skipped: "Skipped",
    created: "Created",
    updated: "Updated",
    failed: "Failed",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes[status] ?? "bg-slate-100 text-slate-600"}`}>
      {labels[status] ?? status}
    </span>
  );
}

function StepIndicator({ current, step, label }: { current: Step; step: Step; label: string }) {
  const done = current > step;
  const active = current === step;
  return (
    <div className="flex items-center gap-2">
      <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold
        ${done ? "bg-emerald-600 text-white" : active ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400"}`}>
        {done ? "✓" : step}
      </div>
      <span className={`text-sm ${active ? "font-semibold text-slate-900 dark:text-white" : done ? "text-emerald-600 dark:text-emerald-400" : "text-slate-500"}`}>
        {label}
      </span>
    </div>
  );
}

function SummaryCard({ label, value, sub, variant = "neutral" }: { label: string; value: number; sub?: string; variant?: "neutral" | "success" | "warning" | "error" }) {
  const color = {
    neutral: "text-slate-900 dark:text-white",
    success: "text-emerald-700 dark:text-emerald-400",
    warning: "text-amber-700 dark:text-amber-400",
    error: "text-red-700 dark:text-red-400",
  }[variant];
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${color}`}>{value.toLocaleString()}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

// ─── Component ─────────────────────────────────────────────────────────────────

export function BulkImportWorkspace() {
  const [step, setStep] = useState<Step>(1);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [conflictStrategy, setConflictStrategy] = useState<BulkImportConflictStrategy>("skip_existing");
  const [defaultAcos, setDefaultAcos] = useState("");

  const [summary, setSummary] = useState<BulkProductImportSummary | null>(null);
  const [commitResult, setCommitResult] = useState<BulkImportCommitResult | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Drop handling ─────────────────────────────────────────────────────────

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }, []);

  // ── Step 1 → 2: upload ────────────────────────────────────────────────────

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await uploadBulkProductFile(file, {
        conflictStrategy,
        workspaceDefaultAcos: defaultAcos ? parseFloat(defaultAcos) : undefined,
      });
      setSummary(result);
      setStep(2);
    } catch (err) {
      setError(formatApiError(err, "Upload failed."));
    } finally {
      setLoading(false);
    }
  }

  // ── Step 4 → 5: commit ────────────────────────────────────────────────────

  async function handleCommit() {
    if (!summary) return;
    setLoading(true);
    setError(null);
    try {
      const result = await commitBulkProductImport(summary.import_id, { conflictStrategy });
      setCommitResult(result);
      setStep(5);
    } catch (err) {
      setError(formatApiError(err, "Creation failed."));
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setStep(1);
    setFile(null);
    setSummary(null);
    setCommitResult(null);
    setError(null);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Bulk product import</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload a CSV or XLSX file to create product profiles in one reviewed action.
          Products are only created after you review and confirm.
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex flex-wrap items-center gap-4">
        <StepIndicator current={step} step={1} label="Upload file" />
        <span className="text-slate-300 dark:text-slate-600">→</span>
        <StepIndicator current={step} step={2} label="Columns detected" />
        <span className="text-slate-300 dark:text-slate-600">→</span>
        <StepIndicator current={step} step={3} label="Validation summary" />
        <span className="text-slate-300 dark:text-slate-600">→</span>
        <StepIndicator current={step} step={4} label="Review exceptions" />
        <span className="text-slate-300 dark:text-slate-600">→</span>
        <StepIndicator current={step} step={5} label="Done" />
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      {/* ── Step 1: upload ───────────────────────────────────────────────── */}
      {step === 1 && (
        <div className="space-y-4">
          <div
            className={`relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 transition-colors
              ${dragOver
                ? "border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/20"
                : "border-slate-300 bg-slate-50 hover:border-slate-400 dark:border-slate-600 dark:bg-slate-800/50"
              }`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              className="sr-only"
              accept=".csv,.xlsx,.tsv"
              onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
            />
            <div className="mb-3 text-4xl">📄</div>
            {file ? (
              <p className="text-sm font-medium text-slate-900 dark:text-white">{file.name}</p>
            ) : (
              <>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Drop a CSV or XLSX file here</p>
                <p className="mt-1 text-xs text-slate-400">or click to browse · max 5 MB</p>
              </>
            )}
          </div>

          {/* Supported columns hint */}
          <details className="text-sm">
            <summary className="cursor-pointer text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
              Supported column names
            </summary>
            <div className="mt-2 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
              <p className="mb-2 text-xs text-slate-500">Column headers are matched automatically. Accepted names include:</p>
              <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-xs">
                <div><strong>Product name:</strong> product name, product title, title, item name, name</div>
                <div><strong>ASIN:</strong> asin, product asin, child asin, advertised product asin</div>
                <div><strong>SKU:</strong> sku, seller sku, merchant sku, product sku</div>
                <div><strong>Target ACOS:</strong> target acos, acos target, target acos %</div>
                <div><strong>Budget:</strong> default budget, daily budget, campaign budget</div>
                <div><strong>Bid:</strong> default bid, starting bid, keyword bid</div>
                <div><strong>Brand:</strong> brand, brand name</div>
                <div><strong>Category:</strong> category, product category</div>
              </div>
            </div>
          </details>

          {/* Options */}
          <div className="grid grid-cols-2 gap-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                If product already exists
              </label>
              <select
                value={conflictStrategy}
                onChange={(e) => setConflictStrategy(e.target.value as BulkImportConflictStrategy)}
                className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-white"
              >
                <option value="skip_existing">Skip (keep existing)</option>
                <option value="update_existing">Update existing</option>
                <option value="create_only_missing">Create only new ones</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                Default target ACOS (if not in file)
              </label>
              <div className="relative mt-1">
                <input
                  type="number"
                  placeholder="e.g. 30"
                  min="1"
                  max="100"
                  value={defaultAcos}
                  onChange={(e) => setDefaultAcos(e.target.value)}
                  className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 pr-7 text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-white"
                />
                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400">%</span>
              </div>
            </div>
          </div>

          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Uploading…" : "Upload and validate"}
          </button>
        </div>
      )}

      {/* ── Step 2: columns detected ─────────────────────────────────────── */}
      {step === 2 && summary && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
            <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
              <h2 className="font-semibold text-slate-900 dark:text-white">Columns detected in &quot;{file?.name}&quot;</h2>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                  <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Original header</th>
                  <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Mapped to</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.detected_columns).map(([original, mapped]) => (
                  <tr key={original} className="border-b border-slate-100 dark:border-slate-700/50">
                    <td className="px-4 py-2 font-mono text-slate-700 dark:text-slate-300">{original}</td>
                    <td className="px-4 py-2">
                      {mapped ? (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400">
                          ✓ {mapped}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">Ignored</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-3">
            <button onClick={() => setStep(3)} className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700">
              Continue →
            </button>
            <button onClick={reset} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700">
              Upload a different file
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: validation summary ───────────────────────────────────── */}
      {step === 3 && summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SummaryCard label="Total rows" value={summary.total_rows} variant="neutral" />
            <SummaryCard label="To create" value={summary.rows_to_create} variant="success" sub="New product profiles" />
            <SummaryCard label="To update" value={summary.rows_to_update} variant="neutral" sub="Existing profiles" />
            <SummaryCard label="Invalid" value={summary.invalid_rows} variant="error" sub="Need correction in source file" />
            <SummaryCard label="To skip" value={summary.rows_to_skip} variant="warning" sub="Invalid, duplicate, or existing" />
          </div>

          {summary.exportable_valid_rows === 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
              No valid rows found. Please fix the errors in your file and re-upload.
            </div>
          ) : (
            <p className="text-sm text-slate-600 dark:text-slate-400">
              <strong>{summary.rows_to_create.toLocaleString()}</strong> product profiles will be created
              {summary.rows_to_update > 0 && <> and <strong>{summary.rows_to_update.toLocaleString()}</strong> will be updated</>}.
              {summary.rows_needing_review > 0 && (
                <> <strong>{summary.rows_needing_review.toLocaleString()}</strong> rows have issues and will be skipped.</>
              )}
            </p>
          )}

          <div className="flex gap-3">
            {summary.rows_needing_review > 0 ? (
              <button onClick={() => setStep(4)} className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700">
                Review {summary.rows_needing_review} exceptions →
              </button>
            ) : (
              <button
                onClick={handleCommit}
                disabled={loading || summary.exportable_valid_rows === 0}
                className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {loading ? "Applying…" : `Apply ${summary.exportable_valid_rows.toLocaleString()} valid rows`}
              </button>
            )}
            <button onClick={reset} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700">
              Start over
            </button>
          </div>
        </div>
      )}

      {/* ── Step 4: review exceptions ────────────────────────────────────── */}
      {step === 4 && summary && (
        <div className="space-y-4">
          <div>
            <h2 className="font-semibold text-slate-900 dark:text-white">Rows needing review</h2>
            <p className="mt-0.5 text-sm text-slate-500">
              These rows will be skipped. Fix them in your source file and re-import.
              Valid rows not listed here will be created or updated according to the existing-product policy.
            </p>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                  <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Row</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Product name</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-400">ASIN / SKU</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Status</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Issues</th>
                </tr>
              </thead>
              <tbody>
                {summary.exception_rows.map((row: BulkProductRow) => (
                  <tr key={row.id} className="border-b border-slate-100 last:border-0 dark:border-slate-700/50">
                    <td className="px-3 py-2 text-slate-500">{row.row_number}</td>
                    <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{row.product_name ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-500">
                      {row.asin || row.sku || "—"}
                    </td>
                    <td className="px-3 py-2"><StatusBadge status={row.status} /></td>
                    <td className="px-3 py-2">
                      {row.validation_errors.length > 0 ? (
                        <ul className="space-y-0.5">
                          {row.validation_errors.map((e, i) => (
                            <li key={i} className="text-xs text-red-600 dark:text-red-400">
                              <span className="font-medium">{e.field}:</span> {e.message}
                              {e.raw_value && <span className="ml-1 text-slate-400">({e.raw_value})</span>}
                            </li>
                          ))}
                        </ul>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleCommit}
              disabled={loading || summary.exportable_valid_rows === 0}
              className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {loading
                ? "Creating…"
                : `Apply ${summary.exportable_valid_rows.toLocaleString()} valid rows (skip ${summary.rows_needing_review} exceptions)`}
            </button>
            <button onClick={reset} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700">
              Start over
            </button>
          </div>
        </div>
      )}

      {/* ── Step 5: done ─────────────────────────────────────────────────── */}
      {step === 5 && commitResult && (
        <div className="space-y-4">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 dark:border-emerald-800 dark:bg-emerald-950/20">
            <div className="mb-3 text-4xl">✅</div>
            <h2 className="text-lg font-semibold text-emerald-800 dark:text-emerald-300">
              {commitResult.created_count.toLocaleString()} product{commitResult.created_count !== 1 ? "s" : ""} created
              {commitResult.updated_count > 0 ? `, ${commitResult.updated_count.toLocaleString()} updated` : ""}
            </h2>
            <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">
              Your product profiles are ready. Upload search term reports to start getting recommendations.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SummaryCard label="Created" value={commitResult.created_count} variant="success" />
            <SummaryCard label="Updated" value={commitResult.updated_count} variant="neutral" />
            <SummaryCard label="Skipped" value={commitResult.skipped_count} variant="neutral" />
            <SummaryCard label="Failed" value={commitResult.failed_count} variant={commitResult.failed_count > 0 ? "error" : "neutral"} />
          </div>

          <div className="flex gap-3">
            <Link
              href="/products"
              className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              View all products →
            </Link>
            <button onClick={reset} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700">
              Import another file
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
