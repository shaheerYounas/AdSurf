import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("recommendations page", () => {
  it("renders decision-focused approval queue controls and safety copy", () => {
    const pageSource = readFileSync("src/app/recommendations/page.tsx", "utf-8");
    const workspaceSource = readFileSync("src/components/recommendations/recommendations-workspace.tsx", "utf-8");

    expect(pageSource).toContain("AI recommendations");
    expect(pageSource).toContain("AI-assisted and rules-engine recommendations");
    expect(pageSource).not.toContain("DeepSeek");
    expect(workspaceSource).toContain("Total recommendations");
    expect(workspaceSource).toContain("Actionable recommendations");
    expect(workspaceSource).toContain("Review-only insights");
    expect(workspaceSource).toContain("Exportable actions");
    expect(workspaceSource).toContain("No live Amazon Ads changes have been made");
    expect(workspaceSource).toContain("Approved actions must be exported and uploaded manually");
    expect(workspaceSource).toContain("Priority");
    expect(workspaceSource).toContain("Recommendation");
    expect(workspaceSource).toContain("Search term");
    expect(workspaceSource).toContain("Campaign / Ad group");
    expect(workspaceSource).toContain("Evidence");
    expect(workspaceSource).toContain("Recommended action");
    expect(workspaceSource).toContain("Confidence");
    expect(workspaceSource).toContain("Exportable");
    expect(workspaceSource).toContain("Status");
    expect(workspaceSource).toContain("Approve");
    expect(workspaceSource).toContain("Reject");
    expect(workspaceSource).toContain("View details");
    expect(workspaceSource).toContain("No Amazon Ads API call will be made");
    expect(workspaceSource).toContain("Raw technical reason");
    expect(workspaceSource).toContain("Advanced technical payload");
    expect(workspaceSource).not.toContain("AI-generated recommendation");
  });
});
