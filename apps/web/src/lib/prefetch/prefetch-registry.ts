/**
 * Registers all prefetchable data sections with the prefetch service.
 * Import this file once at app startup to register every section.
 *
 * Priority ordering (higher = loaded sooner):
 *   100 — Dashboard (landing page, most critical)
 *   90  — Products (frequently navigated)
 *   80  — Uploads / Reports
 *   70  — Agents definitions + configs
 *   60  — Recommendations
 *   50  — Monitoring + workflow
 *
 * Each section loads fetchers one-by-one, never in parallel, so the API
 * is never flooded. The fetcher names are used as cache sub-keys under
 * the section key, e.g. "dashboard:summary".
 */

import { defaultWorkspaceId } from "@/lib/api/client";
import { listAccountImports } from "@/lib/api/account-imports";
import { getDashboardSummary } from "@/lib/api/products";
import { getProductProfiles } from "@/lib/api/products";
import { getAgents, getAgentConfigs, getAgentRuns } from "@/lib/api/agents";
import { getRecommendations } from "@/lib/api/monitoring";
import { getUploads } from "@/lib/api/uploads";
import { registerSection } from "./prefetch-service";

export function registerAllPrefetchSections(workspaceId: string = defaultWorkspaceId): void {
  // ── Dashboard (priority 100 — load first) ────────────────────────
  registerSection({
    key: "dashboard",
    label: "Dashboard",
    priority: 100,
    fetchers: [
      {
        name: "summary",
        fn: () => getDashboardSummary(workspaceId),
        ttlMs: 120_000, // 2 min — dashboard data changes less often
      },
    ],
  });

  // ── Products (priority 90) ───────────────────────────────────────
  registerSection({
    key: "products",
    label: "Products",
    priority: 90,
    fetchers: [
      {
        name: "list",
        fn: () => getProductProfiles(workspaceId),
        ttlMs: 120_000,
      },
    ],
  });

  // ── Uploads / Reports (priority 80) ──────────────────────────────
  registerSection({
    key: "uploads",
    label: "Uploads / Reports",
    priority: 80,
    fetchers: [
      {
        name: "list",
        fn: () => getUploads({ workspaceId }),
        ttlMs: 120_000,
      },
    ],
  });

  // ── Reports (priority 75) ────────────────────────────────────────
  registerSection({
    key: "reports",
    label: "Report Library",
    priority: 75,
    cooldownMs: 350,
    fetchers: [
      {
        name: "uploads",
        fn: () => getUploads({ workspaceId }),
        ttlMs: 120_000,
      },
      {
        name: "account-imports",
        fn: () => listAccountImports(workspaceId),
        ttlMs: 120_000,
      },
      {
        name: "recommendations",
        fn: () => getRecommendations(workspaceId),
        ttlMs: 60_000,
      },
    ],
  });

  // ── Agents (priority 70) ─────────────────────────────────────────
  registerSection({
    key: "agents",
    label: "Agents",
    priority: 70,
    fetchers: [
      {
        name: "definitions",
        fn: () => getAgents(workspaceId),
        ttlMs: 300_000, // 5 min — agent definitions rarely change
      },
      {
        name: "configs",
        fn: () => getAgentConfigs(workspaceId),
        ttlMs: 120_000,
      },
      {
        name: "runs",
        fn: () => getAgentRuns(workspaceId),
        ttlMs: 45_000,
      },
    ],
  });

  // ── Recommendations (priority 60) ────────────────────────────────
  registerSection({
    key: "recommendations",
    label: "Recommendations",
    priority: 60,
    fetchers: [
      {
        name: "list",
        fn: () => getRecommendations(workspaceId),
        ttlMs: 60_000, // 1 min — recommendations change more often
      },
    ],
  });
}

/**
 * Helper: re-register and re-prefetch all sections after a mutation
 * (e.g., after uploading a file, creating a product, approving a recommendation).
 */
export function invalidateAndReprefetchAll(): void {
  // Re-register (no-op if already registered) and the service doesn't
  // auto-clear; the caller should use invalidateSection per key and
  // then call startPrefetching again.
  registerAllPrefetchSections();
}
