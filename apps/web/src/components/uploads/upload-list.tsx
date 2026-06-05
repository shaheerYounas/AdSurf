"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { getUploadParseRuns, getUploads, type ParseRun, type UploadRecord } from "@/lib/api/uploads";

export function UploadList({ productId }: { productId: string }) {
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [parseRunsByUploadId, setParseRunsByUploadId] = useState<Record<string, ParseRun | undefined>>({});
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadUploads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadUploads() {
    setError(null);
    setIsLoading(true);
    try {
      const loadedUploads = await getUploads({ productId, workspaceId });
      setUploads(loadedUploads);
      const parseRuns = await Promise.all(
        loadedUploads.map(async (upload) => {
          if (upload.status !== "processed" && upload.status !== "failed") return [upload.id, undefined] as const;
          const runs = await getUploadParseRuns(upload.id, workspaceId);
          return [upload.id, runs[0]] as const;
        }),
      );
      setParseRunsByUploadId(Object.fromEntries(parseRuns));
    } catch (caught) {
      setError(formatApiError(caught, "Uploads could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
          Workspace ID
          <input id="upload-list-workspace-id" name="upload_list_workspace_id" className="block rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
        </label>
        <Button onClick={loadUploads} type="button" variant="secondary">
          Refresh uploads
        </Button>
      </div>
      {error ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-300/10 dark:text-red-100">{error}</p> : null}
      {isLoading ? (
        <LoadingSpinner className="mt-4" message="Loading upload records" subtext="Fetching file metadata and parse runs" />
      ) : uploads.length ? (
        <ul className="mt-4 divide-y divide-slate-200 dark:divide-white/10">
          {uploads.map((upload) => (
            <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={upload.id}>
              <div>
                <p className="font-medium text-slate-950 dark:text-white">{upload.original_filename}</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {upload.status} / {Math.ceil(upload.file_size_bytes / 1024)} KB
                </p>
                {parseRunsByUploadId[upload.id] ? (
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {parseRunsByUploadId[upload.id]?.parsed_rows_count} parsed rows / {parseRunsByUploadId[upload.id]?.error_rows_count} errors /{" "}
                    {parseRunsByUploadId[upload.id]?.total_columns} columns
                  </p>
                ) : null}
              </div>
              <Link
                className={upload.status === "processed" ? "rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400" : "rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-600 dark:bg-white/10 dark:text-slate-300"}
                href={workflowHref(upload, productId)}
              >
                {upload.status === "processed" ? workflowLabel(upload) : "Waiting"}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">No uploads imported yet.</p>
      )}
    </div>
  );
}

function workflowHref(upload: UploadRecord, productId: string) {
  if (upload.status !== "processed") return `/products/${productId}/uploads`;
  if (upload.source_type === "amazon_ads_sp_search_term_report") return `/products/${productId}/monitoring`;
  return `/products/${productId}/uploads/${upload.id}/mapping`;
}

function workflowLabel(upload: UploadRecord) {
  if (upload.source_type === "amazon_ads_sp_search_term_report") return "Open monitoring";
  return "Open workflow";
}
