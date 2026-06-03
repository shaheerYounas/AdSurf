"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

type ErrorNoticeProps = {
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

export function ErrorNotice({
  title = "Something needs attention",
  message,
  actionLabel,
  onAction,
  className = "",
}: ErrorNoticeProps) {
  return (
    <div
      className={`flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-950 shadow-sm dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100 sm:flex-row sm:items-start sm:justify-between ${className}`}
      role="alert"
    >
      <div className="flex min-w-0 gap-3">
        <AlertCircle aria-hidden="true" className="mt-0.5 shrink-0" size={18} />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 break-words text-sm leading-6 text-rose-800 dark:text-rose-100/85">{message}</p>
        </div>
      </div>
      {onAction ? (
        <Button className="shrink-0" onClick={onAction} size="sm" type="button" variant="secondary">
          <RefreshCw aria-hidden="true" size={14} />
          {actionLabel ?? "Try again"}
        </Button>
      ) : null}
    </div>
  );
}
