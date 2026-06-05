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
    queueMicrotask(() => setPreviousPath(history.at(-1) ?? null));
    writeNavigationHistory([...history, pathname]);
  }, [pathname]);

  if (!previousPath && isRootNavPage(pathname)) {
    return null;
  }

  const targetHref = previousPath ?? fallbackTarget.href;
  const targetLabel = previousPath
    ? getBackNavigationTarget(previousPath).label
    : fallbackTarget.label;

  return (
    <nav className="mb-3 flex items-center" aria-label="Page navigation">
      <Link
        aria-label={`Back to ${targetLabel}`}
        className="inline-flex h-7 items-center gap-1.5 rounded-lg px-2 text-sm font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-indigo-300"
        href={targetHref}
        onClick={(event) => {
          if (!previousPath) return;
          event.preventDefault();
          const trimmed = readNavigationHistory()
            .filter((entry) => entry !== pathname)
            .slice(0, -1);
          writeNavigationHistory(trimmed);
          router.push(previousPath);
        }}
      >
        <ArrowLeft aria-hidden="true" size={14} />
        <span>{targetLabel}</span>
      </Link>
    </nav>
  );
}
