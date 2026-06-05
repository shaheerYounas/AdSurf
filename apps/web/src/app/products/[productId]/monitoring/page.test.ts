import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("product monitoring page", () => {
  it("renders performance report import and recommendation evidence copy", () => {
    const pageSource = readFileSync("src/app/products/[productId]/monitoring/page.tsx", "utf-8");
    const workspaceSource = readFileSync("src/components/monitoring/monitoring-workspace.tsx", "utf-8");

    expect(pageSource).toContain("Performance report to recommendations");
    expect(workspaceSource).toContain("Processed SP Search Term upload");
    expect(workspaceSource).toContain('upload.status === "processed" && upload.source_type === "amazon_ads_sp_search_term_report"');
    expect(workspaceSource).toContain("Import metrics");
    expect(workspaceSource).toContain("Analysis summary");
    expect(workspaceSource).toContain("report rows analyzed");
    expect(workspaceSource).toContain("No Amazon Ads changes have been made");
    expect(workspaceSource).toContain("Pending approval");
    expect(workspaceSource).toContain("Actionable recs");
    expect(workspaceSource).toContain("Negative exact");
    expect(workspaceSource).toContain("Move to exact");
    expect(workspaceSource).toContain("Budget reviews");
    expect(workspaceSource).toContain("Import health");
    expect(workspaceSource).toContain("Detected product groups");
    expect(workspaceSource).toContain("This upload was already imported");
    expect(workspaceSource).toContain("Top recommendations");
    expect(workspaceSource).toContain("DeepSeek AI");
    expect(workspaceSource).toContain("Advanced details");
    expect(workspaceSource).toContain("No live Amazon Ads change executed");
  });
});
