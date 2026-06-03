"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { registerAllPrefetchSections } from "./prefetch-registry";
import { startPrefetching, stopPrefetching, warmSections } from "./prefetch-service";

/**
 * Mount this once in the root layout to register all prefetch sections
 * and kick off background sequential prefetching.
 *
 * Prefetching stops when the component unmounts (e.g., on navigation away
 * or logout). The cache persists in memory across client-side navigations.
 */
export function PrefetchProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    // Register all sections with their fetchers and priorities.
    registerAllPrefetchSections();

    // Start background prefetching — loads sections one-by-one by priority.
    // Use a small delay so the initial page render isn't blocked.
    const timer = setTimeout(() => startPrefetching(), 300);

    return () => {
      clearTimeout(timer);
      stopPrefetching();
    };
  }, []);

  useEffect(() => {
    if (!startedRef.current) return;
    warmSections(routeWarmupSections(pathname));
  }, [pathname]);

  return <>{children}</>;
}

function routeWarmupSections(pathname: string): string[] {
  if (pathname.startsWith("/reports")) return ["reports", "uploads", "recommendations", "products"];
  if (pathname.startsWith("/recommendations")) return ["recommendations", "reports", "dashboard"];
  if (pathname.startsWith("/agents")) return ["agents", "reports", "recommendations"];
  if (pathname.startsWith("/products")) return ["products", "uploads", "reports", "recommendations"];
  return ["dashboard", "products", "reports", "recommendations"];
}
