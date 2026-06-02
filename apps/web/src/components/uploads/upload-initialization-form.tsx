"use client";

import { CheckCircle2, Loader2, UploadCloud } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { apiBaseUrl, defaultWorkspaceId, localAuthHeaders, newIdempotencyKey } from "@/lib/api/client";
import {
  ACCEPTED_UPLOAD_EXTENSIONS,
  MAX_UPLOAD_FILE_SIZE_BYTES,
  hasAcceptedUploadExtension,
} from "@/lib/upload-constraints";

type UploadInitializationFormProps = {
  productId: string;
};

type InitResponse = {
  upload_id: string;
  storage_path: string;
  upload_url: string;
  upload_url_expires_at: string;
  status: string;
};

type ConfirmResponse = {
  upload_id: string;
  status: string;
  job_id: string;
};

type ParseRun = {
  id: string;
  status: string;
  parsed_rows_count: number;
  error_rows_count: number;
  total_rows: number;
  total_columns: number;
};

export function UploadInitializationForm({ productId }: UploadInitializationFormProps) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initResult, setInitResult] = useState<InitResponse | null>(null);
  const [confirmResult, setConfirmResult] = useState<ConfirmResponse | null>(null);
  const [parseRuns, setParseRuns] = useState<ParseRun[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const fileSummary = useMemo(() => {
    if (!file) return "No file selected";
    return `${file.name} / ${Math.ceil(file.size / 1024)} KB`;
  }, [file]);

  function validateSelectedFile(selectedFile: File | null) {
    if (!selectedFile) return "Choose a CSV or Excel file.";
    if (!hasAcceptedUploadExtension(selectedFile.name)) return "Use .csv, .xls, or .xlsx.";
    if (selectedFile.size > MAX_UPLOAD_FILE_SIZE_BYTES) return "File must be 25 MB or smaller.";
    return null;
  }

  async function initializeUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setConfirmResult(null);

    const validationError = validateSelectedFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!workspaceId.trim()) {
      setError("Workspace ID is required for the local Batch 3 shell.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/products/${productId}/uploads/init`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": newIdempotencyKey(),
          ...localAuthHeaders(workspaceId),
        },
        body: JSON.stringify({
          original_filename: file?.name,
          mime_type: file?.type || mimeTypeForFilename(file?.name ?? ""),
          file_size_bytes: file?.size,
          source_type: "competitor_keyword_research",
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Upload initialization failed.");
      setInitResult(body.data);
      setParseRuns([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload initialization failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function confirmUpload() {
    if (!initResult || !file) {
      setError("Initialize an upload and choose a file before confirming.");
      return;
    }
    setError(null);
    setIsConfirming(true);
    try {
      const objectResponse = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${initResult.upload_id}/object`, {
        method: "PUT",
        headers: localAuthHeaders(workspaceId),
        body: file,
      });
      const objectBody = await objectResponse.json();
      if (!objectResponse.ok) throw new Error(objectBody.error?.message ?? "File upload failed.");
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${initResult.upload_id}/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": newIdempotencyKey(),
          ...localAuthHeaders(workspaceId),
        },
        body: JSON.stringify({}),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "Upload confirmation failed.");
      setConfirmResult(body.data);
      await processLocalJobs();
      await loadParseRuns(initResult.upload_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload confirmation failed.");
    } finally {
      setIsConfirming(false);
    }
  }

  async function processLocalJobs() {
    if (process.env.NODE_ENV === "production") return;
    const response = await fetch(`${apiBaseUrl}/v1/dev/process-upload-jobs`, { method: "POST", headers: localAuthHeaders(workspaceId) });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.error?.message ?? "Local upload worker processing failed.");
  }

  async function loadParseRuns(uploadId: string) {
    const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/uploads/${uploadId}/parse-runs`, {
      headers: localAuthHeaders(workspaceId),
    });
    if (!response.ok) throw new Error("Upload parse runs could not be loaded.");
    const body = await response.json();
    setParseRuns(body.data ?? []);
  }

  return (
    <form className="space-y-5 rounded-lg border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70" onSubmit={initializeUpload}>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(220px,280px)]">
        <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
          Raw keyword file
          <input
            accept={ACCEPTED_UPLOAD_EXTENSIONS.join(",")}
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-full file:border-0 file:bg-slate-950 file:px-3 file:py-1 file:text-white dark:border-white/10 dark:bg-white/5 dark:text-white dark:file:bg-white dark:file:text-slate-950"
            onChange={(event) => {
              const selectedFile = event.target.files?.[0] ?? null;
              setFile(selectedFile);
              setError(validateSelectedFile(selectedFile));
              setInitResult(null);
              setConfirmResult(null);
            }}
            type="file"
          />
          <span className="block text-xs font-normal text-slate-500 dark:text-slate-400">CSV/XLS/XLSX, 25 MB max</span>
        </label>
        <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
          Workspace ID
          <input
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white"
            onChange={(event) => setWorkspaceId(event.target.value)}
            placeholder="Workspace UUID"
            value={workspaceId}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-white/10">
        <p className="text-sm text-slate-600 dark:text-slate-300">{fileSummary}</p>
        <div className="flex gap-2">
          <Button className="inline-flex items-center gap-2" disabled={isSubmitting} type="submit">
            {isSubmitting ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <UploadCloud aria-hidden="true" size={16} />}
            {isSubmitting ? "Initializing..." : "Init upload"}
          </Button>
          <Button
            className="inline-flex items-center gap-2 bg-emerald-700 disabled:bg-slate-300"
            disabled={!initResult || isConfirming}
            onClick={confirmUpload}
            type="button"
          >
            {isConfirming ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : <CheckCircle2 aria-hidden="true" size={16} />}
            {isConfirming ? "Confirming..." : "Confirm upload"}
          </Button>
        </div>
      </div>

      {error ? <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-300/10 dark:text-red-100">{error}</p> : null}

      {initResult ? (
        <div className="space-y-2 rounded-md bg-slate-50 p-3 text-sm dark:bg-white/5">
          <p className="font-medium text-slate-900 dark:text-white">Upload status: {initResult.status}</p>
          <p className="break-all font-mono text-xs text-slate-600 dark:text-slate-300">{initResult.storage_path}</p>
          {process.env.NODE_ENV !== "production" ? (
            <p className="break-all font-mono text-xs text-slate-500 dark:text-slate-400">{initResult.upload_url}</p>
          ) : null}
        </div>
      ) : null}

      {confirmResult ? (
        <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-300/10 dark:text-emerald-100">
          Queued job {confirmResult.job_id} with status {confirmResult.status}.
        </div>
      ) : null}

      <div className="rounded-md border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
        <p className="font-medium text-slate-900 dark:text-white">
          Parsing prepares your uploaded file for manual column mapping. After parsing succeeds, open column mapping to map search term,
          search volume, and competitor rank columns.
        </p>
        {parseRuns[0] ? (
          <>
            <dl className="mt-3 grid gap-2 sm:grid-cols-4">
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Parse status</dt>
                <dd className="font-medium">{parseRuns[0].status}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Parsed rows</dt>
                <dd className="font-medium">{parseRuns[0].parsed_rows_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Error rows</dt>
                <dd className="font-medium">{parseRuns[0].error_rows_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Columns</dt>
                <dd className="font-medium">{parseRuns[0].total_columns}</dd>
              </div>
            </dl>
            {parseRuns[0].status === "succeeded" && initResult ? (
              <a
                className="mt-3 inline-flex rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white dark:bg-indigo-300 dark:text-indigo-950"
                href={`/products/${productId}/uploads/${initResult.upload_id}/mapping`}
              >
                Open column mapping
              </a>
            ) : null}
          </>
        ) : null}
      </div>
    </form>
  );
}

function mimeTypeForFilename(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".csv")) return "text/csv";
  if (lower.endsWith(".xls")) return "application/vnd.ms-excel";
  return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
}
