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
    <div className={cn("relative", className)} ref={containerRef}>
      {label && (
        <span className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300">
          {label}
        </span>
      )}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(!open)}
        className={cn(
          "flex min-h-11 w-full items-center justify-between gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-950 shadow-sm transition",
          "hover:border-slate-300",
          "focus-visible:border-indigo-400 focus-visible:ring-2 focus-visible:ring-indigo-100 focus-visible:outline-none",
          "dark:border-white/10 dark:bg-slate-950/40 dark:text-white dark:hover:border-white/20 dark:focus-visible:border-indigo-400 dark:focus-visible:ring-indigo-400/20",
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
            "shrink-0 text-slate-400 transition-transform dark:text-slate-500",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
            <div
              ref={dropdownRef}
              className="absolute left-0 top-full z-50 mt-1 max-h-72 w-full overflow-auto rounded-2xl border border-slate-200 bg-white py-1 shadow-xl shadow-slate-950/10 dark:border-white/10 dark:bg-slate-900"
              role="listbox"
            >
              {placeholder && (
                <div className="px-3 py-2 text-xs font-semibold text-slate-400 dark:text-slate-500">
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
                    "flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm font-medium transition",
                    option.value === value
                      ? "bg-indigo-50 text-indigo-800 dark:bg-indigo-400/10 dark:text-indigo-200"
                      : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/10",
                    option.disabled && "cursor-not-allowed opacity-40",
                  )}
                >
                  <span className="flex-1 truncate">{option.label ?? humanize(option.value)}</span>
                  {option.value === value && <Check size={16} className="shrink-0 text-indigo-600 dark:text-indigo-400" />}
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
