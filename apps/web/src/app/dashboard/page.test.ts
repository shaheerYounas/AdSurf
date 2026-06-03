import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("dashboard page", () => {
  it("renders professional loading and safety UI", () => {
    const source = readFileSync("src/components/dashboard/dashboard-overview.tsx", "utf-8");

    expect(source).toContain("getDashboardSummary");
    expect(source).toContain("Loader2");
    expect(source).toContain("Gathering your workspace data");
    expect(source).toContain("formatApiError");
    expect(source).toContain("ErrorNotice");
    expect(source).toContain("Recommendation only");
    expect(source).toContain("Does not change Amazon Ads account");
    expect(source).toContain("DatabaseZap");
  });

  it("keeps the initial dashboard fetch alive long enough for database-backed data", () => {
    const source = readFileSync("src/app/dashboard/page.tsx", "utf-8");

    expect(source).toContain("setTimeout(() => controller.abort(), 10000)");
  });
});
