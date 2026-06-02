import type { Metadata } from "next";
import { AppSidebar } from "@/components/app-sidebar";
import { BackNavigationButton } from "@/components/navigation/back-navigation-button";
import { OnboardingTour } from "@/components/onboarding/onboarding-tour";
import { ThemeProvider, themeBootstrapScript } from "@/components/theme/theme-provider";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { SafetyNotice } from "@/components/ui/safety-notice";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amazon Ads AI Control Center",
  description: "AI-native Amazon Ads recommendation control center with human-approved execution boundaries."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Set the theme class before paint so we never flash the wrong colors. */}
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body className="min-h-screen text-slate-950 antialiased dark:text-white">
        <ThemeProvider>
          <div className="soft-grid-bg flex min-h-screen">
            <AppSidebar />
            <main className="min-w-0 flex-1">
              <div className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-white/60 bg-white/75 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/60 sm:px-5 sm:py-4 md:hidden">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">AdSurf AI Control Center</p>
                  <p className="truncate text-xs text-slate-500 dark:text-slate-400">Recommendation only · human approval required</p>
                </div>
                <ThemeToggle compact />
              </div>
              <div className="mx-auto max-w-[1800px] px-4 py-8 sm:px-6 sm:py-10 lg:px-10">
                <BackNavigationButton />
                {children}
                <footer className="mt-10 flex justify-center border-t border-slate-200 pt-5 dark:border-white/10">
                  <SafetyNotice variant="compact" />
                </footer>
              </div>
            </main>
          </div>
          <OnboardingTour />
        </ThemeProvider>
      </body>
    </html>
  );
}
