"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

type ModalProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
};

export function Modal({ open, onClose, title, description, children, size = "md" }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div
        className={`relative max-h-[92vh] w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 dark:border-white/10 dark:bg-slate-950 ${modalSizeClass(size)}`}
        role="dialog"
        aria-modal="true"
      >
        {(title || description) && (
          <div className="border-b border-slate-100 px-6 py-4 dark:border-white/10">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                {title && <h2 className="text-base font-semibold text-slate-950 dark:text-white">{title}</h2>}
                {description && <p className="mt-1 text-sm leading-5 text-slate-600 dark:text-slate-300">{description}</p>}
              </div>
              <button
                onClick={onClose}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:text-white"
                type="button"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        )}
        <div className="max-h-[calc(92vh-7rem)] overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

function modalSizeClass(size: NonNullable<ModalProps["size"]>) {
  if (size === "sm") return "max-w-md";
  if (size === "lg") return "max-w-2xl";
  if (size === "xl") return "max-w-4xl";
  return "max-w-lg";
}
