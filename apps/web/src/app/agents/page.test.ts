import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("agent control center page", () => {
  it("renders agent controls, workflow, configuration, and safety copy", () => {
    const pageSource = readFileSync("src/app/agents/page.tsx", "utf-8");
    const workspaceSource = readFileSync("src/components/agents/agent-control-center.tsx", "utf-8");
    const layoutSource = readFileSync("src/app/layout.tsx", "utf-8");

    expect(pageSource).toContain("Agent Control Center");
    expect(layoutSource).toContain("Agents");
    expect(workspaceSource).toContain("Agent Overview");
    expect(workspaceSource).toContain("Agent Workflow Graph");
    expect(workspaceSource).toContain("Agent Timeline");
    expect(workspaceSource).toContain("Pause");
    expect(workspaceSource).toContain("Resume");
    expect(workspaceSource).toContain("Stop");
    expect(workspaceSource).toContain("Rerun from here");
    expect(workspaceSource).toContain("Strictness");
    expect(workspaceSource).toContain("Confidence");
    expect(workspaceSource).toContain("can_mutate_live_amazon_ads");
    expect(workspaceSource).toContain("cannot_approve_or_reject");
  });
});
