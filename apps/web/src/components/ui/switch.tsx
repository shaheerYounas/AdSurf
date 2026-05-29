"use client";

import { cn } from "@/lib/utils";

type SwitchProps = {
  label?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  helperText?: string;
  className?: string;
};

export function Switch({
  label,
  checked,
  onChange,
  disabled,
  helperText,
  className,
}: SwitchProps) {
  return (
    <label
      className={cn(
        "relative inline-flex items-center gap-3",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className,
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-950",
          checked
            ? "bg-indigo-600 dark:bg-indigo-500"
            : "bg-slate-200 dark:bg-white/20",
        )}
      >
        <span
          className={cn(
            "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ease-in-out",
            checked ? "translate-x-5" : "translate-x-0.5",
          )}
        />
      </button>
      {(label || helperText) && (
        <span className="min-w-0">
          {label && (
            <span className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
              {label}
            </span>
          )}
          {helperText && (
            <span className="block text-xs text-slate-500 dark:text-slate-400">
              {helperText}
            </span>
          )}
        </span>
      )}
    </label>
  );
}