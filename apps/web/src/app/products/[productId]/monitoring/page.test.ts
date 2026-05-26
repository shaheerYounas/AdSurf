import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("product monitoring page", () => {
  it("renders performance report import and recommendation evidence copy", () => {
    const pageSource = readFileSync("src/app/products/[productId]/monitoring/page.tsx", "utf-8");
    const workspaceSource = readFileSync("src/components/monitoring/monitoring-workspace.tsx", "utf-8");

    expect(pageSource).toContain("Performance report to recommendations");
    expect(workspaceSource).toContain("Processed SP Search Term upload");
    expect(workspaceSource).toContain("Import metrics");
    expect(workspaceSource).toContain("Pending approval");
    expect(workspaceSource).toContain("Negative exact");
    expect(workspaceSource).toContain("Move to exact");
    expect(workspaceSource).toContain("Budget reviews");
    expect(workspaceSource).toContain("Top recommendations");
  });
});
