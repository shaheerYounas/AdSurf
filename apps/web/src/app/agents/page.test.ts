import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("agent control center page", () => {
  it("renders agent controls, workflow, configuration, and safety copy", () => {
    const pageSource = readFileSync("src/app/agents/page.tsx", "utf-8");
    const workspaceSource = readFileSync("src/components/agents/agent-control-center.tsx", "utf-8");
    const inspectorSource = readFileSync("src/components/agents/agent-inspector.tsx", "utf-8");
    const timelineSource = readFileSync("src/components/agents/agent-trace-timeline.tsx", "utf-8");
    const layoutSource = readFileSync("src/app/layout.tsx", "utf-8");
    const sidebarSource = readFileSync("src/components/app-sidebar.tsx", "utf-8");

    expect(pageSource).toContain("Agent Control Center");
    expect(layoutSource).toContain("AppSidebar");
    expect(sidebarSource).toContain("Agents");
    expect(sidebarSource).toContain("Agent Ops");
    expect(sidebarSource).toContain("Main menu");
    expect(workspaceSource).toContain("Agent Team Dashboard");
    expect(workspaceSource).toContain("Visual Workflow Canvas");
    expect(workspaceSource).toContain("Human Approval Checkpoints");
    expect(workspaceSource).toContain("Agent Templates");
    expect(workspaceSource).toContain("Simple Mode");
    expect(workspaceSource).toContain("Advanced Mode");
    expect(workspaceSource).toContain("Report Detection Agent");
    expect(workspaceSource).toContain("Product Resolution Agent");
    expect(workspaceSource).toContain("Budget Allocation Agent");
    expect(workspaceSource).toContain("Human Approval Agent");
    expect(workspaceSource).toContain("Pause");
    expect(workspaceSource).toContain("Resume");
    expect(workspaceSource).toContain("Stop");
    expect(workspaceSource).toContain("Rerun failed");
    expect(workspaceSource).toContain("Recommendation only");
    expect(workspaceSource).toContain("Requires human approval");
    expect(workspaceSource).toContain("No live Amazon Ads change executed");
    expect(inspectorSource).toContain("Configuration");
    expect(inspectorSource).toContain("Prompt / Business Goal");
    expect(inspectorSource).toContain("Recommendations");
    expect(inspectorSource).toContain("Permissions");
    expect(inspectorSource).toContain("Trace");
    expect(inspectorSource).toContain("Safety");
    expect(inspectorSource).toContain("Cannot execute Amazon Ads API changes");
    expect(timelineSource).toContain("Trace Timeline");
    expect(timelineSource).toContain("model_called");
    expect(timelineSource).toContain("fallback_used");
  });
});
