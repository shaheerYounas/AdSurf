"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  ArrowLeft,
  Bot,
  ClipboardCheck,
  FileText,
  GitBranch,
  LayoutDashboard,
  LibraryBig,
  ListChecks,
  PackageSearch,
  PlusCircle,
  Settings,
  Sparkles,
  Upload,
  Users,
} from "lucide-react";
import { defaultWorkspaceId } from "@/lib/api/client";
import { ThemeToggle } from "@/components/theme/theme-toggle";

type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  helper?: string;
  opensAgentPanel?: boolean;
};

export const mainNavGroups: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, helper: "Workspace overview" },
      { href: "/agents", label: "Agents", icon: Bot, helper: "Control AI workflow", opensAgentPanel: true },
      { href: "/recommendations", label: "Recommendations", icon: ListChecks, helper: "Approval queue" },
    ],
  },
  {
    label: "Products",
    items: [
      { href: "/products", label: "Products", icon: PackageSearch, helper: "ASIN profiles" },
      { href: "/products/new", label: "New product", icon: PlusCircle, helper: "Start setup" },
      { href: "/products/bulk", label: "Bulk import", icon: Upload, helper: "CSV / XLSX upload" },
    ],
  },
  {
    label: "Data",
    items: [
      { href: "/reports", label: "Report Library", icon: LibraryBig, helper: "Uploaded report files" },
    ],
  },
];

const agentNavItems = [
  { href: "/dashboard", label: "Workspace", icon: Users },
  { href: "/agents#reports", label: "Reports", icon: FileText },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/agents#workflow-canvas", label: "Workflows", icon: GitBranch },
  { href: "/recommendations", label: "Recommendations", icon: Sparkles },
  { href: "/agents#approval-checkpoints", label: "Approvals", icon: ClipboardCheck },
  { href: "/agents#agent-settings", label: "Settings", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [panel, setPanel] = useState<"main" | "agents">(pathname.startsWith("/agents") ? "agents" : "main");

  return (
    // md (tablet): icon-only 64px wide flex column
    // lg (desktop): full 256px wide flex column with labels
    <aside className="sticky top-0 hidden h-screen shrink-0 overflow-y-auto border-r border-white/60 bg-white/75 shadow-2xl shadow-slate-950/5 backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/50 md:flex md:w-16 md:flex-col md:px-2 md:py-5 lg:w-64 lg:px-4">
      {panel === "agents" ? (
        <AgentPanel onBack={() => setPanel("main")} />
      ) : (
        <MainPanel onOpenAgents={() => setPanel("agents")} pathname={pathname} />
      )}
    </aside>
  );
}

function MainPanel({ pathname, onOpenAgents }: { pathname: string; onOpenAgents: () => void }) {
  return (
    <div className="flex flex-1 flex-col">
      <BrandCard eyebrow="Control Center" title="AdSurf AI" />
      <nav aria-label="Main navigation" className="space-y-5">
        {mainNavGroups.map((group) => (
          <div key={group.label}>
            {/* Group label: visible on desktop only */}
            <p className="mb-1.5 hidden px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500 lg:block">
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
                    aria-current={active ? "page" : undefined}
                    className={`group flex items-center justify-center gap-3 rounded-xl px-2 py-2 text-sm font-semibold transition-all duration-150 lg:justify-start lg:px-3 ${
                      active
                        ? "bg-gradient-to-r from-indigo-50 to-violet-50 text-indigo-900 shadow-sm dark:from-indigo-300/15 dark:to-violet-300/10 dark:text-indigo-100"
                        : "text-slate-700 hover:bg-white/80 hover:text-slate-950 hover:shadow-sm dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
                    }`}
                    href={item.href}
                    key={item.href}
                    onClick={item.opensAgentPanel ? onOpenAgents : undefined}
                    title={item.label}
                  >
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-all duration-150 ${
                        active
                          ? "border-indigo-200 bg-indigo-600 text-white shadow-sm shadow-indigo-600/25 dark:border-indigo-400/30 dark:bg-indigo-500 dark:shadow-indigo-500/20"
                          : "border-slate-200 bg-white text-slate-500 group-hover:border-indigo-200 group-hover:text-indigo-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-400"
                      }`}
                    >
                      <Icon aria-hidden="true" size={15} />
                    </span>
                    {/* Label + helper: visible on desktop only */}
                    <span className="hidden min-w-0 lg:block">
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
      {/* Theme toggle at bottom — tablet only (desktop has it in BrandCard) */}
      <div className="mt-4 flex justify-center pt-2 lg:hidden">
        <ThemeToggle compact />
      </div>
    </div>
  );
}

function AgentPanel({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="mb-5 rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <button
            className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700 outline-none transition hover:border-indigo-200 hover:text-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 lg:px-3"
            onClick={onBack}
            title="Main menu"
            type="button"
          >
            <ArrowLeft size={14} />
            <span className="hidden lg:inline">Main menu</span>
          </button>
          <ThemeToggle compact />
        </div>
        <div className="hidden items-center gap-2.5 lg:flex">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-600/25 dark:from-indigo-500 dark:to-violet-500">
            <Sparkles aria-hidden="true" size={16} />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-950 dark:text-white">AdSurf</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Agent Ops</p>
          </div>
        </div>
        <div className="mt-4 hidden lg:block">
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">Workspace ID</p>
          <p className="mt-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-[11px] font-semibold text-slate-700 dark:border-white/10 dark:bg-slate-950/60 dark:text-slate-300">
            {defaultWorkspaceId}
          </p>
        </div>
      </div>

      <nav aria-label="Agent Ops navigation" className="space-y-0.5">
        {agentNavItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              className="flex min-h-10 items-center justify-center gap-3 rounded-xl px-2 text-sm font-semibold text-slate-700 outline-none transition hover:bg-white/80 hover:text-slate-950 focus-visible:ring-2 focus-visible:ring-indigo-300 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white lg:justify-start lg:px-3"
              href={item.href}
              key={item.label}
              title={item.label}
            >
              <Icon aria-hidden="true" size={15} />
              <span className="hidden lg:block">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

function BrandCard({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <>
      {/* Desktop: full brand card with theme toggle */}
      <div className="mb-6 hidden rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5 lg:block">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/30 dark:from-indigo-500 dark:to-violet-500 dark:shadow-indigo-500/20">
              <Sparkles aria-hidden="true" size={16} />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
                {eyebrow}
              </p>
              <h1 className="mt-0.5 truncate text-base font-semibold tracking-tight text-slate-950 dark:text-white">
                {title}
              </h1>
            </div>
          </div>
          <ThemeToggle compact />
        </div>
      </div>
      {/* Tablet: icon only */}
      <div className="mb-5 flex justify-center lg:hidden">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/30 dark:from-indigo-500 dark:to-violet-500 dark:shadow-indigo-500/20">
          <Sparkles aria-hidden="true" size={18} />
        </div>
      </div>
    </>
  );
}
