import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AppSidebar } from "@/components/app-sidebar";
import { MobileHeader } from "@/components/navigation/mobile-header";
import { BackNavigationButton } from "@/components/navigation/back-navigation-button";
import { OnboardingTour } from "@/components/onboarding/onboarding-tour";
import { ThemeProvider } from "@/components/theme/theme-provider";
import type { ResolvedTheme } from "@/components/theme/theme-provider";
import { SafetyNotice } from "@/components/ui/safety-notice";
import { PrefetchProvider } from "@/lib/prefetch/prefetch-provider";
import "./globals.css";

function resolveThemeFromCookie(cookieValue: string | null): ResolvedTheme {
  if (cookieValue === "light" || cookieValue === "dark") return cookieValue;
  return "light";
}

export const metadata: Metadata = {
  title: "Amazon Ads AI Control Center",
  description: "AI-native Amazon Ads recommendation control center with human-approved execution boundaries.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies();
  const resolvedTheme = resolveThemeFromCookie(cookieStore.get("adsurf-theme")?.value ?? null);

  return (
    <html lang="en" className={resolvedTheme === "dark" ? "dark" : ""} style={{ colorScheme: resolvedTheme }} suppressHydrationWarning>
      <head />
      <body className="min-h-screen text-slate-950 antialiased dark:text-white">
        <a className="skip-link" href="#main-content">Skip to content</a>
        <ThemeProvider>
          <PrefetchProvider>
            <div className="soft-grid-bg flex min-h-screen">
              <AppSidebar />
              <main aria-label="Main content" className="min-w-0 flex-1" id="main-content">
                <MobileHeader />
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
          </PrefetchProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
