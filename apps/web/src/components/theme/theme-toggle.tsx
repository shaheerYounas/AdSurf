"use client";

import { useEffect, useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme, type Theme } from "@/components/theme/theme-provider";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

/**
 * Pill-shaped theme switcher with three options. The active option is highlighted
 * via the brand color and the others remain in the surface tone. Keyboard-accessible,
 * announces state via aria-pressed for screen readers.
 */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, resolved, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Avoid hydration mismatch: only render the actual selected state once we're on the client.
  useEffect(() => {
    queueMicrotask(() => setMounted(true));
  }, []);

  if (compact) {
    // Single-button mode: clicking flips between light and dark, ignoring system.
    const Icon = mounted && resolved === "dark" ? Sun : Moon;
    const label = mounted
      ? (resolved === "dark" ? "Switch to light mode" : "Switch to dark mode")
      : "Toggle theme";
    return (
      <button
        type="button"
        aria-label={label}
        title={label}
        onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}
        className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 outline-none transition hover:-translate-y-0.5 hover:border-indigo-200 hover:text-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-300/40 dark:hover:text-white"
      >
        {mounted ? <Icon size={16} /> : <Monitor size={16} />}
      </button>
    );
  }

  return (
    <div
      className="inline-flex items-center rounded-full border border-slate-200 bg-white p-1 shadow-sm dark:border-white/10 dark:bg-white/5"
      role="group"
      aria-label="Theme"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = mounted && theme === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            aria-label={`${label} theme`}
            title={`${label} theme`}
            onClick={() => setTheme(value)}
            className={`inline-flex h-8 min-w-8 items-center justify-center gap-1.5 rounded-full px-2.5 text-xs font-semibold outline-none transition focus-visible:ring-2 focus-visible:ring-indigo-300 ${active ? "bg-indigo-600 text-white shadow-sm dark:bg-indigo-300 dark:text-indigo-950" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10"}`}
          >
            <Icon size={14} />
            <span className="hidden sm:inline">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
