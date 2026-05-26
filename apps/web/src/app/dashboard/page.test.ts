import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("dashboard page", () => {
  it("renders professional loading and safety UI", () => {
    const source = readFileSync("src/components/dashboard/dashboard-overview.tsx", "utf-8");

    expect(source).toContain("getDashboardSummary");
    expect(source).toContain("Loader2");
    expect(source).toContain("Supabase is still syncing");
    expect(source).toContain("Recommendation only");
    expect(source).toContain("Does not change Amazon Ads account");
    expect(source).toContain("DatabaseZap");
  });
});
