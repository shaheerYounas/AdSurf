"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Bot, ClipboardCheck, FileText, GitBranch, LayoutDashboard, ListChecks, PackageSearch, PlusCircle, Settings, ShieldCheck, Sparkles, Users } from "lucide-react";
import { defaultWorkspaceId } from "@/lib/api/client";
import { ThemeToggle } from "@/components/theme/theme-toggle";

const mainNavItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, helper: "Workspace overview" },
  { href: "/agents", label: "Agents", icon: Bot, helper: "Control AI workflow", opensAgentPanel: true },
  { href: "/products", label: "Products", icon: PackageSearch, helper: "ASIN profiles" },
  { href: "/products/new", label: "New product", icon: PlusCircle, helper: "Start setup" },
  { href: "/recommendations", label: "Recommendations", icon: ListChecks, helper: "Approval queue" },
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

  useEffect(() => {
    if (pathname.startsWith("/agents")) setPanel("agents");
  }, [pathname]);

  return (
    <aside className="sticky top-0 hidden h-screen w-80 shrink-0 overflow-y-auto border-r border-white/60 bg-white/70 px-5 py-6 shadow-2xl shadow-slate-950/5 backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/45 md:block">
      {panel === "agents" ? <AgentPanel onBack={() => setPanel("main")} /> : <MainPanel pathname={pathname} onOpenAgents={() => setPanel("agents")} />}
    </aside>
  );
}

function MainPanel({ pathname, onOpenAgents }: { pathname: string; onOpenAgents: () => void }) {
  return (
    <>
      <BrandCard eyebrow="Control Center" title="AdSurf AI" />
      <nav className="space-y-2" aria-label="Main navigation">
        {mainNavItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
          return (
            <Link
              className={`group flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-semibold transition hover:-translate-y-0.5 hover:bg-white/80 hover:text-slate-950 hover:shadow-lg hover:shadow-slate-950/5 dark:hover:bg-white/10 dark:hover:text-white ${active ? "bg-white/90 text-slate-950 shadow-lg shadow-slate-950/5 dark:bg-white/10 dark:text-white" : "text-slate-700 dark:text-slate-300"}`}
              href={item.href}
              key={item.href}
              onClick={item.opensAgentPanel ? onOpenAgents : undefined}
            >
              <span className={`flex h-10 w-10 items-center justify-center rounded-xl border transition ${active ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-300/40 dark:bg-indigo-300/15 dark:text-indigo-100" : "border-slate-200 bg-white text-slate-600 group-hover:border-indigo-200 group-hover:text-indigo-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"}`}>
                <Icon aria-hidden="true" size={17} />
              </span>
              <span>
                <span className="block">{item.label}</span>
                <span className="block text-xs font-medium text-slate-400 dark:text-slate-500">{item.helper}</span>
              </span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}

function AgentPanel({ onBack }: { onBack: () => void }) {
  return (
    <>
      <div className="mb-5 rounded-[1.75rem] border border-slate-200/70 bg-white/80 p-5 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5">
        <div className="mb-5 flex items-center justify-between gap-3">
          <button className="inline-flex min-h-10 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 outline-none transition hover:border-indigo-200 hover:text-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200" onClick={onBack} type="button">
            <ArrowLeft size={16} /> Main menu
          </button>
          <ThemeToggle compact />
        </div>
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-950/20 dark:bg-white dark:text-slate-950">
            <Sparkles aria-hidden="true" size={20} />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-950 dark:text-white">AdSurf</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Agent Ops</p>
          </div>
        </div>
        <div className="mt-5">
          <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">Workspace</p>
          <p className="mt-2 rounded-2xl border border-slate-200 bg-white px-3 py-3 font-mono text-xs font-semibold text-slate-800 dark:border-white/10 dark:bg-slate-950/60 dark:text-slate-200">{defaultWorkspaceId}</p>
        </div>
      </div>

      <nav className="space-y-1" aria-label="Agent Ops navigation">
        {agentNavItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link className="flex min-h-11 items-center gap-3 rounded-2xl px-3 text-sm font-semibold text-slate-700 outline-none transition hover:bg-white/80 hover:text-slate-950 focus-visible:ring-2 focus-visible:ring-indigo-300 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white" href={item.href} key={item.label}>
              <Icon aria-hidden="true" size={17} /> {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold leading-5 text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100">
        <p>Recommendation only</p>
        <p className="mt-1">Requires human approval</p>
        <p className="mt-1">No live Amazon Ads change executed</p>
      </div>
    </>
  );
}

function BrandCard({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="mb-8 rounded-[1.75rem] border border-slate-200/70 bg-white/80 p-5 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-950/20 dark:bg-white dark:text-slate-950">
            <Sparkles aria-hidden="true" size={20} />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">{eyebrow}</p>
            <h1 className="mt-1 truncate text-lg font-semibold tracking-tight text-slate-950 dark:text-white">{title}</h1>
          </div>
        </div>
        <ThemeToggle compact />
      </div>
      <div className="mt-5 rounded-2xl border border-emerald-200/80 bg-emerald-50/80 px-3 py-2 text-xs leading-5 text-emerald-900 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-100">
        <span className="inline-flex items-center gap-1 font-semibold"><ShieldCheck size={14} /> Safe mode</span>
        <p>AI recommends. Humans approve. No live Amazon Ads changes execute here.</p>
      </div>
    </div>
  );
}
