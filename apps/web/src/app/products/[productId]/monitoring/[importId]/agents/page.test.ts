import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("import agent control center page", () => {
  it("renders import-level agent graph route", () => {
    const pageSource = readFileSync("src/app/products/[productId]/monitoring/[importId]/agents/page.tsx", "utf-8");
    const monitoringSource = readFileSync("src/components/monitoring/monitoring-workspace.tsx", "utf-8");

    expect(pageSource).toContain("Import workflow");
    expect(pageSource).toContain("Agent Control Center");
    expect(monitoringSource).toContain("Open Agent Control Center");
  });
});
