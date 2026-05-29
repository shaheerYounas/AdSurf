"use client";

import { Loader2, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type LoadingSpinnerProps = {
  /** The loading message displayed below the spinner. */
  message?: string;
  /** Optional subtext for longer operations. */
  subtext?: string;
  /** Icon component; defaults to Loader2 with animate-spin. */
  icon?: LucideIcon;
  /** When true the icon spins (only applies when icon is unset). */
  animate?: boolean;
  /** Additional class for the wrapper so callers can control spacing and alignment. */
  className?: string;
  /** When provided, renders a compact inline spinner suitable for button children. */
  size?: "default" | "sm" | "lg";
  /** When true, only renders the icon (no message). */
  iconOnly?: boolean;
};

const sizeMap = {
  sm: { icon: 14, text: "text-xs" },
  default: { icon: 20, text: "text-sm" },
  lg: { icon: 28, text: "text-base" },
} as const;

export function LoadingSpinner({
  message = "Loading",
  subtext,
  icon: Icon,
  animate = true,
  className = "",
  size = "default",
  iconOnly = false,
}: LoadingSpinnerProps) {
  const dims = sizeMap[size];

  if (iconOnly) {
    const IconComponent = Icon ?? Loader2;
    return (
      <IconComponent
        aria-hidden="true"
        className={animate && !Icon ? "animate-spin" : ""}
        size={dims.icon}
      />
    );
  }

  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-white/10 dark:bg-slate-950/70 ${className}`}
      role="status"
      aria-live="polite"
    >
      {Icon ? (
        <Icon aria-hidden="true" size={dims.icon} />
      ) : (
        <Loader2 aria-hidden="true" className={animate ? "animate-spin" : ""} size={dims.icon} />
      )}
      <p className={`font-semibold text-slate-700 dark:text-slate-200 ${dims.text}`}>
        {message}
      </p>
      {subtext ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">{subtext}</p>
      ) : null}
    </div>
  );
}

/**
 * Renders a set of pulsing placeholder blocks to mimic table rows or cards while data loads.
 */
export function LoadingSkeleton({
  lines = 5,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div
      className={`space-y-3 p-6 ${className}`}
      role="status"
      aria-live="polite"
    >
      <span className="sr-only">Loading content</span>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-10 animate-pulse rounded-2xl bg-slate-200 dark:bg-white/10"
          style={{ width: `${75 + Math.random() * 20}%` }}
        />
      ))}
    </div>
  );
}

/**
 * Compact inline text suitable for table empty states while data is still loading.
 */
export function LoadingLine({ text = "Loading data..." }: { text?: string }) {
  return (
    <p
      className="flex items-center gap-2 px-5 py-8 text-sm text-slate-500 dark:text-slate-400"
      role="status"
    >
      <Loader2 aria-hidden="true" className="animate-spin" size={16} />
      {text}
    </p>
  );
}