import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "success" | "warning" | "danger" | "accent" | "neutral";
type Size = "default" | "sm";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold shadow-sm transition-all duration-150 hover:-translate-y-px hover:shadow-md active:scale-[0.97] active:translate-y-0 active:shadow-sm disabled:pointer-events-none disabled:translate-y-0 disabled:active:scale-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-950";

const variants: Record<Variant, string> = {
  primary:
    "bg-gradient-to-b from-indigo-500 to-indigo-700 text-white shadow-indigo-600/25 hover:from-indigo-400 hover:to-indigo-600 hover:shadow-indigo-500/30 focus-visible:ring-indigo-400 dark:from-indigo-500 dark:to-indigo-700 dark:shadow-indigo-500/20",
  secondary:
    "border border-slate-200 bg-white text-slate-800 shadow-none hover:border-slate-300 hover:bg-slate-50 hover:shadow-sm focus-visible:ring-slate-400 dark:border-white/10 dark:bg-white/10 dark:text-white dark:hover:bg-white/15 dark:hover:border-white/20",
  success:
    "bg-gradient-to-b from-emerald-500 to-emerald-700 text-white shadow-emerald-600/20 hover:from-emerald-400 hover:to-emerald-600 focus-visible:ring-emerald-400 dark:from-emerald-500 dark:to-emerald-700",
  warning:
    "bg-gradient-to-b from-amber-400 to-amber-600 text-white shadow-amber-500/20 hover:from-amber-300 hover:to-amber-500 focus-visible:ring-amber-400 dark:from-amber-400 dark:to-amber-600 dark:text-amber-950",
  danger:
    "bg-gradient-to-b from-red-500 to-red-700 text-white shadow-red-600/20 hover:from-red-400 hover:to-red-600 focus-visible:ring-red-400 dark:from-red-500 dark:to-red-700",
  accent:
    "bg-gradient-to-b from-violet-500 to-violet-700 text-white shadow-violet-600/20 hover:from-violet-400 hover:to-violet-600 focus-visible:ring-violet-400 dark:from-violet-500 dark:to-violet-700",
  neutral:
    "bg-gradient-to-b from-slate-700 to-slate-900 text-white shadow-slate-900/20 hover:from-slate-600 hover:to-slate-800 focus-visible:ring-slate-500 dark:from-slate-600 dark:to-slate-800",
};

const sizes: Record<Size, string> = {
  default: "min-h-10",
  sm: "min-h-8 px-3 text-xs",
};

export function Button({ className, variant = "primary", size = "default", ...props }: ButtonProps) {
  return <button className={cn(base, variants[variant], sizes[size], className)} {...props} />;
}
