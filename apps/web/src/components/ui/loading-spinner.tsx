"use client";

import { Loader2, type LucideIcon } from "lucide-react";

type LoadingSpinnerProps = {
  message?: string;
  subtext?: string;
  icon?: LucideIcon;
  animate?: boolean;
  className?: string;
  size?: "default" | "sm" | "lg";
  iconOnly?: boolean;
};

const sizeMap = {
  sm: { icon: 14, text: "text-xs" },
  default: { icon: 20, text: "text-sm" },
  lg: { icon: 28, text: "text-base" },
} as const;

const skeletonWidths = ["92%", "84%", "88%", "78%", "90%", "82%", "86%", "80%"];

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
      className={`flex flex-col items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm dark:border-white/10 dark:bg-slate-950/70 ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-100 bg-slate-50 dark:border-white/10 dark:bg-white/5">
        {Icon ? (
          <Icon aria-hidden="true" className="text-slate-500 dark:text-slate-400" size={dims.icon} />
        ) : (
          <Loader2
            aria-hidden="true"
            className={`text-indigo-500 dark:text-indigo-300 ${animate ? "animate-spin" : ""}`}
            size={dims.icon}
          />
        )}
      </div>
      <div>
        <p className={`font-semibold text-slate-700 dark:text-slate-200 ${dims.text}`}>{message}</p>
        {subtext ? (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtext}</p>
        ) : null}
      </div>
    </div>
  );
}

export function LoadingSkeleton({
  lines = 5,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-3 p-6 ${className}`} role="status" aria-live="polite">
      <span className="sr-only">Loading content</span>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="relative h-10 overflow-hidden rounded-2xl bg-slate-200 dark:bg-white/10"
          style={{ width: skeletonWidths[i % skeletonWidths.length] }}
        >
          <div className="shimmer-sweep absolute inset-0 bg-gradient-to-r from-transparent via-white/60 to-transparent dark:via-white/15" />
        </div>
      ))}
    </div>
  );
}

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
