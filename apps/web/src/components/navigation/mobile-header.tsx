"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Menu, Sparkles, X } from "lucide-react";
import { mainNavGroups } from "@/components/app-sidebar";
import { ThemeToggle } from "@/components/theme/theme-toggle";

export function MobileHeader() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close drawer on route change
  useEffect(() => {
    const timeout = window.setTimeout(() => setOpen(false), 0);
    return () => window.clearTimeout(timeout);
  }, [pathname]);

  // Lock body scroll while drawer is open
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = open ? "hidden" : prev;
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  // Dismiss on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <>
      {/* Sticky top bar — visible on mobile only */}
      <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-white/60 bg-white/80 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/65 md:hidden">
        <button
          aria-expanded={open}
          aria-label="Open navigation menu"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-indigo-200 hover:text-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-400/30 dark:hover:text-indigo-300"
          onClick={() => setOpen(true)}
          type="button"
        >
          <Menu size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-950 dark:text-white">AdSurf AI</p>
          <p className="truncate text-xs text-slate-500 dark:text-slate-400">Recommendation only</p>
        </div>
        <ThemeToggle compact />
      </div>

      {/* Drawer overlay */}
      {open && (
        <div
          aria-label="Navigation menu"
          aria-modal="true"
          className="fixed inset-0 z-50 md:hidden"
          role="dialog"
        >
          {/* Backdrop */}
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />

          {/* Side panel */}
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col overflow-y-auto border-r border-white/20 bg-white/95 py-5 shadow-2xl backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/98">
            {/* Panel header */}
            <div className="mb-5 flex items-center justify-between gap-2 px-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/30 dark:from-indigo-500 dark:to-violet-500 dark:shadow-indigo-500/20">
                  <Sparkles aria-hidden="true" size={16} />
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
                    Control Center
                  </p>
                  <p className="text-sm font-semibold text-slate-950 dark:text-white">AdSurf AI</p>
                </div>
              </div>
              <button
                aria-label="Close navigation menu"
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
                onClick={() => setOpen(false)}
                type="button"
              >
                <X size={16} />
              </button>
            </div>

            {/* Navigation */}
            <nav aria-label="Mobile navigation" className="flex-1 space-y-5 px-3">
              {mainNavGroups.map((group) => (
                <div key={group.label}>
                  <p className="mb-1.5 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                    {group.label}
                  </p>
                  <div className="space-y-0.5">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      const active =
                        pathname === item.href ||
                        (item.href !== "/dashboard" && pathname.startsWith(item.href));
                      return (
                        <Link
                          key={item.href}
                          aria-current={active ? "page" : undefined}
                          className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all duration-150 ${
                            active
                              ? "bg-gradient-to-r from-indigo-50 to-violet-50 text-indigo-900 shadow-sm dark:from-indigo-300/15 dark:to-violet-300/10 dark:text-indigo-100"
                              : "text-slate-700 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
                          }`}
                          href={item.href}
                        >
                          <span
                            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-all duration-150 ${
                              active
                                ? "border-indigo-200 bg-indigo-600 text-white shadow-sm shadow-indigo-600/25 dark:border-indigo-400/30 dark:bg-indigo-500"
                                : "border-slate-200 bg-white text-slate-500 group-hover:border-indigo-200 group-hover:text-indigo-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-400"
                            }`}
                          >
                            <Icon aria-hidden="true" size={15} />
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate">{item.label}</span>
                            {item.helper ? (
                              <span className="block truncate text-xs font-normal text-slate-400 dark:text-slate-500">
                                {item.helper}
                              </span>
                            ) : null}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
