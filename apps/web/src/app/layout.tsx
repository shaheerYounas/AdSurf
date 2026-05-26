import type { Metadata } from "next";
import Link from "next/link";
import { LayoutDashboard, ListChecks, PackageSearch, PlusCircle } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amazon Ads AI Control Center",
  description: "MVP foundation shell for Amazon Ads workflow automation."
};

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/products", label: "Products", icon: PackageSearch },
  { href: "/products/new", label: "New product", icon: PlusCircle },
  { href: "/recommendations", label: "Recommendations", icon: ListChecks }
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-950">
        <div className="flex min-h-screen">
          <aside className="hidden w-72 border-r border-slate-200 bg-white px-5 py-6 md:block">
            <div className="mb-8">
              <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Control Center</p>
              <h1 className="mt-2 text-xl font-semibold">Amazon Ads AI</h1>
            </div>
            <nav className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                <Link
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                  href={item.href}
                  key={item.href}
                >
                  <Icon aria-hidden="true" size={16} />
                  {item.label}
                </Link>
                );
              })}
            </nav>
          </aside>
          <main className="flex-1">
            <div className="border-b border-slate-200 bg-white px-5 py-4 md:hidden">
              <p className="text-sm font-semibold">Amazon Ads AI</p>
            </div>
            <div className="mx-auto max-w-6xl px-5 py-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
