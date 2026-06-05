"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import {
  getBackNavigationTarget,
  isInternalNavigationPath,
  isRootNavPage,
  normalizePathname,
} from "@/lib/navigation/back-navigation";

const historyStorageKey = "adsurf:navigation-history";
const maxHistoryEntries = 20;

function readNavigationHistory(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(historyStorageKey) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isInternalNavigationPath).map(normalizePathname) : [];
  } catch {
    return [];
  }
}

function writeNavigationHistory(history: string[]) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(historyStorageKey, JSON.stringify(history.slice(-maxHistoryEntries)));
}

export function BackNavigationButton() {
  const router = useRouter();
  const pathname = normalizePathname(usePathname());
  const fallbackTarget = useMemo(() => getBackNavigationTarget(pathname), [pathname]);
  const [previousPath, setPreviousPath] = useState<string | null>(null);

  useEffect(() => {
    const history = readNavigationHistory().filter((entry) => entry !== pathname);
    setPreviousPath(history.at(-1) ?? null);
    writeNavigationHistory([...history, pathname]);
  }, [pathname]);

  // On root nav pages with no real history, there is nothing useful to go back
  // to — the sidebar is already the navigation for these pages.
  if (!previousPath && isRootNavPage(pathname)) {
    return null;
  }

  const targetHref = previousPath ?? fallbackTarget.href;

  // Derive a human-readable label from the actual destination path so the
  // button always says where it goes, e.g. "← Products" or "← Monitoring".
  const targetLabel = previousPath
    ? getBackNavigationTarget(previousPath).label
    : fallbackTarget.label;

  return (
    <nav className="mb-5 flex items-center gap-3" aria-label="Page navigation">
      <Link
        aria-label={`Back to ${targetLabel}`}
        className="group inline-flex min-h-10 max-w-full items-center gap-2 rounded-xl border border-slate-200/80 bg-white/85 px-3 py-2 text-sm font-semibold text-slate-800 shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:border-indigo-200 hover:bg-white hover:text-indigo-700 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/10 dark:text-slate-100 dark:hover:border-indigo-300/40 dark:hover:bg-white/15 dark:hover:text-white"
        href={targetHref}
        onClick={(event) => {
          if (!previousPath) return;
          event.preventDefault();
          // Pop the current page and the destination from history before
          // navigating back so the destination's useEffect sees the correct
          // prior entry instead of re-inserting the current page.
          const trimmed = readNavigationHistory()
            .filter((entry) => entry !== pathname)
            .slice(0, -1);
          writeNavigationHistory(trimmed);
          router.push(previousPath);
        }}
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-white shadow-sm transition group-hover:bg-indigo-600 dark:bg-white dark:text-slate-950 dark:group-hover:bg-indigo-200">
          <ArrowLeft aria-hidden="true" size={15} />
        </span>
        <span className="truncate">{targetLabel}</span>
      </Link>
    </nav>
  );
}
