import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "success" | "warning" | "danger" | "accent" | "neutral";
type Size = "default" | "sm";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-lg active:translate-y-0 disabled:pointer-events-none disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-950";

const variants: Record<Variant, string> = {
  // Default brand action — high-contrast indigo in both themes.
  primary:
    "bg-indigo-600 text-white hover:bg-indigo-500 focus-visible:ring-indigo-400 dark:bg-indigo-500 dark:text-white dark:hover:bg-indigo-400",
  // Quiet surface action — low emphasis, still visible against both backgrounds.
  secondary:
    "border border-slate-200 bg-white text-slate-900 shadow-none hover:bg-slate-100 focus-visible:ring-slate-400 dark:border-white/10 dark:bg-white/10 dark:text-white dark:hover:bg-white/20",
  // Positive action.
  success:
    "bg-emerald-600 text-white hover:bg-emerald-500 focus-visible:ring-emerald-400 dark:bg-emerald-500 dark:text-white dark:hover:bg-emerald-400",
  // Caution action.
  warning:
    "bg-amber-500 text-white hover:bg-amber-400 focus-visible:ring-amber-400 dark:bg-amber-400 dark:text-amber-950 dark:hover:bg-amber-300",
  // Destructive action.
  danger:
    "bg-red-600 text-white hover:bg-red-500 focus-visible:ring-red-400 dark:bg-red-500 dark:text-white dark:hover:bg-red-400",
  // Approvals / violet accent.
  accent:
    "bg-violet-600 text-white hover:bg-violet-500 focus-visible:ring-violet-400 dark:bg-violet-500 dark:text-white dark:hover:bg-violet-400",
  // Stop / neutral dark surface.
  neutral:
    "bg-slate-800 text-white hover:bg-slate-700 focus-visible:ring-slate-500 dark:bg-slate-700 dark:text-white dark:hover:bg-slate-600",
};

const sizes: Record<Size, string> = {
  default: "min-h-10",
  sm: "min-h-9 px-3 text-xs",
};

export function Button({ className, variant = "primary", size = "default", ...props }: ButtonProps) {
  return <button className={cn(base, variants[variant], sizes[size], className)} {...props} />;
}