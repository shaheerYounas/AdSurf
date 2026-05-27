import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("recommendations page", () => {
  it("renders recommendation approval controls and safety copy", () => {
    const pageSource = readFileSync("src/app/recommendations/page.tsx", "utf-8");
    const workspaceSource = readFileSync("src/components/recommendations/recommendations-workspace.tsx", "utf-8");

    expect(pageSource).toContain("AI recommendations");
    expect(workspaceSource).toContain("Approve");
    expect(workspaceSource).toContain("Reject");
    expect(workspaceSource).toContain("no Amazon Ads change is executed");
    expect(workspaceSource).toContain("Evidence");
    expect(workspaceSource).toContain("AI reasoning");
    expect(workspaceSource).toContain("Proposed action");
    expect(workspaceSource).toContain("AI-generated recommendation");
    expect(workspaceSource).toContain("deepseek_ai");
    expect(workspaceSource).toContain("add_negative_exact");
    expect(workspaceSource).toContain("data_quality_review");
    expect(workspaceSource).toContain("budget_review");
    expect(workspaceSource).toContain("Does not change Amazon Ads account");
    expect(workspaceSource).toContain("No live Amazon Ads change executed");
    expect(workspaceSource).toContain("confidence");
  });
});
