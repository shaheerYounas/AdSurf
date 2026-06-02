import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("competitor workflow page", () => {
  it("supports phase-specific workflow and agentic Amazon browser verification copy", () => {
    const pageSource = readFileSync("src/app/products/[productId]/competitors/page.tsx", "utf-8");
    const workflowSource = readFileSync("src/components/competitor/competitor-workflow.tsx", "utf-8");

    expect(pageSource).toContain("CompetitorWorkflow");
    expect(workflowSource).toContain("Full flow");
    expect(workflowSource).toContain("Phase 1");
    expect(workflowSource).toContain("Phase 2");
    expect(workflowSource).toContain("Phase 3");
    expect(workflowSource).toContain("Agentic Amazon browser verification");
    expect(workflowSource).toContain("Run verification agent");
    expect(workflowSource).toContain("verifyCompetitorKeywordsAgentic");
    expect(workflowSource).toContain("Simulate 14 days");
  });
});
