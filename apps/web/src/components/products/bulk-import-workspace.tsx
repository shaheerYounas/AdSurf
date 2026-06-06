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
  getBulkProductImport,
  commitBulkProductImport,
  type BulkProductImportSummary,
  type BulkProductImportWithRows,
  type BulkProductRow,
  type BulkImportConflictStrategy,
  type BulkImportCommitResult,
} from "@/lib/api/products";
import { ApiError, formatApiError } from "@/lib/api/client";
import { detectAmazonFileType } from "@/lib/amazon-file-detector";

// ─── Types ─────────────────────────────────────────────────────────────────────

type Step = 1 | 2 | 3 | 4 | 5;

// ─── Helpers ───────────────────────────────────────────────────────────────────

function _importToSummary(imp: BulkProductImportWithRows): BulkProductImportSummary {
  const rowsWithProduct = imp.rows.filter(r => r.status === "valid" && r.product_id);
  const exceptionRows = imp.rows.filter(r => r.status !== "valid");
  return {
    import_id: imp.id,
    status: imp.status,
    total_rows: imp.total_rows,
    valid_rows: imp.valid_rows,
    invalid_rows: imp.invalid_rows,
    duplicate_in_file_rows: imp.duplicate_in_file_rows,
    already_exists_rows: imp.already_exists_rows,
    rows_needing_review: imp.invalid_rows + imp.duplicate_in_file_rows + imp.already_exists_rows,
    exportable_valid_rows: imp.valid_rows,
    rows_to_create: imp.valid_rows - rowsWithProduct.length,
    rows_to_update: rowsWithProduct.length,
    rows_to_skip: imp.invalid_rows + imp.duplicate_in_file_rows + imp.already_exists_rows,
    warning_rows: 0,
    detected_columns: imp.detected_columns_json,
    exception_rows: exceptionRows.slice(0, 50),
  };
}

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

function ColumnMappingBadge({ mapped }: { mapped: string }) {
  if (mapped === "source_evidence") {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700 dark:bg-sky-900/20 dark:text-sky-300">
        Preserved as source evidence
      </span>
    );
  }
  if (mapped) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400">
        ✓ {mapped}
      </span>
    );
  }
  return <span className="text-xs text-slate-400">Not used for product setup</span>;
}

// ─── Component ─────────────────────────────────────────────────────────────────

export function BulkImportWorkspace() {
  const [step, setStep] = useState<Step>(1);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicateImportId, setDuplicateImportId] = useState<string | null>(null);
  const [spReportDetected, setSpReportDetected] = useState(false);
  const [bulkSheetDetected, setBulkSheetDetected] = useState(false);

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
    setDuplicateImportId(null);
    setSpReportDetected(false);
    setBulkSheetDetected(false);

    // Client-side routing — intercept misrouted files before any network call
    const detection = detectAmazonFileType(file.name);
    if (detection.type === "BULK_OPERATIONS") {
      setBulkSheetDetected(true);
      setLoading(false);
      return;
    }
    if (detection.type === "SP_SEARCH_TERM_REPORT" ||
        detection.type === "SP_TARGETING_REPORT" ||
        detection.type === "SP_CAMPAIGN_REPORT" ||
        detection.type === "SP_ADVERTISED_PRODUCT" ||
        detection.type === "SB_REPORT" ||
        detection.type === "SD_REPORT") {
      setSpReportDetected(true);
      setLoading(false);
      return;
    }
    try {
      const result = await uploadBulkProductFile(file, {
        conflictStrategy,
        workspaceDefaultAcos: defaultAcos ? parseFloat(defaultAcos) : undefined,
      });
      setSummary(result);
      setStep(2);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_FILE") {
        const id = err.details?.existing_import_id;
        if (typeof id === "string") {
          setDuplicateImportId(id);
          return;
        }
      }
      if (err instanceof ApiError && err.code === "SP_REPORT_DETECTED") {
        setSpReportDetected(true);
        return;
      }
      setError(formatApiError(err, "Upload failed."));
    } finally {
      setLoading(false);
    }
  }

  async function handleContinueExistingImport() {
    if (!duplicateImportId) return;
    setLoading(true);
    setError(null);
    try {
      const imp = await getBulkProductImport(duplicateImportId);
      setDuplicateImportId(null);
      if (imp.status === "completed") {
        setSummary(_importToSummary(imp));
        setCommitResult({
          import_id: imp.id,
          status: imp.status,
          created_count: imp.created_rows,
          updated_count: imp.updated_rows,
          skipped_count: imp.skipped_rows,
          failed_count: imp.failed_rows,
          created_product_ids: [],
          updated_product_ids: [],
        });
        setStep(5);
      } else {
        setSummary(_importToSummary(imp));
        setStep(2);
      }
    } catch (err) {
      setError(formatApiError(err, "Could not load existing import."));
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
    setDuplicateImportId(null);
    setSpReportDetected(false);
    setBulkSheetDetected(false);
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

      {spReportDetected && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-5 dark:border-indigo-700/50 dark:bg-indigo-950/20">
          <div className="flex items-start gap-4">
            <div className="shrink-0 text-2xl">📊</div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-indigo-900 dark:text-indigo-200">
                This is a Sponsored Products Search Term Report
              </p>
              <p className="mt-1 text-sm text-indigo-700 dark:text-indigo-400">
                Search Term Reports contain ad performance data — impressions, clicks, spend, sales, and ACOS per keyword.
                They&apos;re not product catalogs. The right workflow analyses each search term against your target ACOS and tells you exactly:
              </p>
              <ul className="mt-2 space-y-1 text-sm text-indigo-700 dark:text-indigo-400 list-none">
                <li>✦ Which converting search terms to harvest as exact match keywords</li>
                <li>✦ Which high-spend, zero-order terms to add as negatives</li>
                <li>✦ Which bids to raise or lower based on actual ACOS vs your target</li>
              </ul>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  href="/products"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
                >
                  Go to Monitoring Import →
                </Link>
                <button
                  onClick={reset}
                  className="rounded-lg border border-indigo-300 px-4 py-2 text-sm font-medium text-indigo-800 hover:bg-indigo-100 dark:border-indigo-600 dark:text-indigo-300 dark:hover:bg-indigo-900/20"
                >
                  Upload a different file
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {bulkSheetDetected && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-5 dark:border-violet-700/50 dark:bg-violet-950/20">
          <div className="flex items-start gap-4">
            <div className="shrink-0 text-2xl">📂</div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-violet-900 dark:text-violet-200">
                This is an Amazon Bulk Operations file
              </p>
              <p className="mt-1 text-sm text-violet-700 dark:text-violet-400">
                Bulk Operations files contain your full account structure — campaigns, ad groups, keywords, and current bids.
                They&apos;re not product catalogs. Use the Bulk Sheet Viewer to inspect your account and analyse keyword bids.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  href="/bulk-sheet"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700"
                >
                  Open Bulk Sheet Viewer →
                </Link>
                <button
                  onClick={reset}
                  className="rounded-lg border border-violet-300 px-4 py-2 text-sm font-medium text-violet-800 hover:bg-violet-100 dark:border-violet-600 dark:text-violet-300 dark:hover:bg-violet-900/20"
                >
                  Upload a different file
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {duplicateImportId && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 dark:border-amber-700/50 dark:bg-amber-950/20">
          <div className="flex items-start gap-4">
            <div className="shrink-0 text-2xl">📋</div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-amber-900 dark:text-amber-200">
                This file has already been imported
              </p>
              <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
                An import for this exact file already exists. You can pick up where it left off, or start fresh with a different file.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={handleContinueExistingImport}
                  disabled={loading}
                  className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  {loading ? "Loading…" : "Continue with existing import"}
                </button>
                <button
                  onClick={reset}
                  className="rounded-lg border border-amber-300 px-4 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100 dark:border-amber-600 dark:text-amber-300 dark:hover:bg-amber-900/20"
                >
                  Upload a different file
                </button>
              </div>
            </div>
          </div>
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
                      <ColumnMappingBadge mapped={mapped} />
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
