"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn, humanize } from "@/lib/utils";

type SelectOption = {
  value: string;
  label?: string;
  disabled?: boolean;
};

type SelectProps = {
  label?: string;
  value: string;
  options: string[] | SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  helperText?: string;
  disabled?: boolean;
};

function toOptions(raw: string[] | SelectOption[]): SelectOption[] {
  if (typeof raw[0] === "string") {
    return (raw as string[]).map((v) => ({ value: v }));
  }
  return raw as SelectOption[];
}

export function Select({
  label,
  value,
  options: rawOptions,
  onChange,
  placeholder,
  className,
  helperText,
  disabled,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const options = toOptions(rawOptions);
  const selected = options.find((o) => o.value === value);
  const selectOption = useCallback(
    (option: SelectOption) => {
      if (option.disabled) return;
      onChange(option.value);
      setOpen(false);
    },
    [onChange],
  );

  useEffect(() => {
    if (!open) return;

    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      const insideTrigger = containerRef.current?.contains(target);
      const insideDropdown = dropdownRef.current?.contains(target);
      if (!insideTrigger && !insideDropdown) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
    }
  }, [open]);

  return (
    <div className={cn("relative min-w-[10.5rem]", className)} ref={containerRef}>
      {label && (
        <span className="mb-2 block text-xs font-bold text-slate-600 dark:text-slate-300">
          {label}
        </span>
      )}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(!open)}
        className={cn(
          "flex min-h-12 w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-left text-sm font-bold text-slate-950 shadow-sm transition",
          "hover:border-indigo-200 hover:bg-slate-50",
          "focus-visible:border-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-100",
          "dark:border-white/10 dark:bg-slate-950/70 dark:text-white dark:shadow-black/20 dark:hover:border-indigo-300/35 dark:hover:bg-white/5 dark:focus-visible:border-indigo-300 dark:focus-visible:ring-indigo-400/20",
          open && "border-indigo-300 bg-indigo-50/60 dark:border-indigo-300/40 dark:bg-indigo-300/10",
          disabled && "cursor-not-allowed opacity-50",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={cn("truncate", !selected && !placeholder && "text-slate-400 dark:text-slate-500")}>
          {selected ? (selected.label ?? humanize(selected.value)) : placeholder ?? "Select..."}
        </span>
        <ChevronDown
          size={16}
          className={cn(
            "shrink-0 text-slate-500 transition-transform duration-200 dark:text-slate-400",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
            <div
              ref={dropdownRef}
              className="absolute left-0 top-full z-50 mt-2 max-h-72 min-w-full w-max max-w-[min(22rem,calc(100vw-2rem))] overflow-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-2xl shadow-slate-950/15 dark:border-indigo-300/20 dark:bg-slate-900/95 dark:shadow-black/40"
              role="listbox"
            >
              {placeholder && (
                <div className="px-3 py-2 text-xs font-bold text-slate-400 dark:text-slate-500">
                  {placeholder}
                </div>
              )}
              {options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  disabled={option.disabled}
                  role="option"
                  aria-selected={option.value === value}
                  onPointerDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    selectOption(option);
                  }}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    selectOption(option);
                  }}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    selectOption(option);
                  }}
                  className={cn(
                    "flex w-full min-w-0 items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition",
                    option.value === value
                      ? "bg-indigo-50 text-indigo-800 dark:bg-indigo-300/15 dark:text-indigo-100"
                      : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/10",
                    option.disabled && "cursor-not-allowed opacity-40",
                  )}
                >
                  <span className="min-w-0 flex-1 whitespace-nowrap">{option.label ?? humanize(option.value)}</span>
                  <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full", option.value === value ? "bg-indigo-600 text-white dark:bg-indigo-300 dark:text-indigo-950" : "text-transparent")}>
                    <Check size={13} />
                  </span>
                </button>
              ))}
            </div>
      )}

      {helperText && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{helperText}</p>
      )}
    </div>
  );
}
