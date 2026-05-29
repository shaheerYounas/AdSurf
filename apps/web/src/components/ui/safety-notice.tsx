"use client";

import { FileText, ShieldCheck, Sparkles } from "lucide-react";

type SafetyNoticeVariant = "banner" | "compact" | "pill";

type SafetyNoticeProps = {
  variant?: SafetyNoticeVariant;
  className?: string;
};

const messages = [
  { icon: ShieldCheck, text: "Recommendation only" },
  { icon: Sparkles, text: "Requires human approval" },
  { icon: FileText, text: "No live Amazon Ads change executed" },
] as const;

const variantStyles: Record<SafetyNoticeVariant, { wrapper: string; item: string; iconSize: number }> = {
  banner: {
    wrapper:
      "flex flex-wrap gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-semibold text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
    item: "inline-flex items-center gap-2",
    iconSize: 16,
  },
  compact: {
    wrapper:
      "inline-flex flex-wrap gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
    item: "inline-flex items-center gap-1.5",
    iconSize: 14,
  },
  pill: {
    wrapper: "flex flex-wrap gap-2",
    item: "inline-flex items-center gap-2 rounded-full border border-emerald-300 bg-emerald-100 px-3 py-1.5 text-xs font-semibold text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
    iconSize: 14,
  },
};

export function SafetyNotice({ variant = "compact", className = "" }: SafetyNoticeProps) {
  const styles = variantStyles[variant];

  return (
    <div className={`${styles.wrapper} ${className}`}>
      {messages.map(({ icon: Icon, text }) => (
        <span className={styles.item} key={text}>
          <Icon size={styles.iconSize} />
          {text}
        </span>
      ))}
    </div>
  );
}