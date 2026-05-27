import type { Metadata } from "next";
import { AppSidebar } from "@/components/app-sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amazon Ads AI Control Center",
  description: "AI-native Amazon Ads recommendation control center with human-approved execution boundaries."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen text-slate-950 antialiased dark:text-white">
        <div className="soft-grid-bg flex min-h-screen">
          <AppSidebar />
          <main className="min-w-0 flex-1">
            <div className="sticky top-0 z-20 border-b border-white/60 bg-white/75 px-5 py-4 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/60 md:hidden">
              <p className="text-sm font-semibold">AdSurf AI Control Center</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Recommendation only · human approval required</p>
            </div>
            <div className="mx-auto max-w-[1800px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
