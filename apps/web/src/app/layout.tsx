import type { Metadata } from "next";
import Link from "next/link";
import { Bot, LayoutDashboard, ListChecks, PackageSearch, PlusCircle, ShieldCheck, Sparkles } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amazon Ads AI Control Center",
  description: "AI-native Amazon Ads recommendation control center with human-approved execution boundaries."
};

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, helper: "Workspace overview" },
  { href: "/agents", label: "Agents", icon: Bot, helper: "Control AI workflow" },
  { href: "/products", label: "Products", icon: PackageSearch, helper: "ASIN profiles" },
  { href: "/products/new", label: "New product", icon: PlusCircle, helper: "Start setup" },
  { href: "/recommendations", label: "Recommendations", icon: ListChecks, helper: "Approval queue" }
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen text-slate-950 antialiased dark:text-white">
        <div className="soft-grid-bg flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-80 shrink-0 border-r border-white/60 bg-white/70 px-5 py-6 shadow-2xl shadow-slate-950/5 backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/45 md:block">
            <div className="mb-8 rounded-[1.75rem] border border-slate-200/70 bg-white/80 p-5 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-950/20 dark:bg-white dark:text-slate-950">
                  <Sparkles aria-hidden="true" size={20} />
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Control Center</p>
                  <h1 className="mt-1 text-lg font-semibold tracking-tight text-slate-950 dark:text-white">AdSurf AI</h1>
                </div>
              </div>
              <div className="mt-5 rounded-2xl border border-emerald-200/80 bg-emerald-50/80 px-3 py-2 text-xs leading-5 text-emerald-900 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-100">
                <span className="inline-flex items-center gap-1 font-semibold"><ShieldCheck size={14} /> Safe mode</span>
                <p>AI recommends. Humans approve. No live Amazon Ads changes execute here.</p>
              </div>
            </div>
            <nav className="space-y-2">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    className="group flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-semibold text-slate-700 transition hover:-translate-y-0.5 hover:bg-white/80 hover:text-slate-950 hover:shadow-lg hover:shadow-slate-950/5 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
                    href={item.href}
                    key={item.href}
                  >
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition group-hover:border-indigo-200 group-hover:text-indigo-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
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
          </aside>
          <main className="min-w-0 flex-1">
            <div className="sticky top-0 z-20 border-b border-white/60 bg-white/75 px-5 py-4 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/60 md:hidden">
              <p className="text-sm font-semibold">AdSurf AI Control Center</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Recommendation only · human approval required</p>
            </div>
            <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
