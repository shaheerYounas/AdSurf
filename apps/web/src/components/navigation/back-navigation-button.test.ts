import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("global previous-page control", () => {
  it("is mounted from the root layout and uses deterministic fallback navigation", () => {
    const layoutSource = readFileSync("src/app/layout.tsx", "utf-8");
    const buttonSource = readFileSync("src/components/navigation/back-navigation-button.tsx", "utf-8");

    expect(layoutSource).toContain("BackNavigationButton");
    expect(buttonSource).toContain("getBackNavigationTarget");
    expect(buttonSource).toContain("sessionStorage");
  });

  it("hides on root nav pages when there is no real history", () => {
    const buttonSource = readFileSync("src/components/navigation/back-navigation-button.tsx", "utf-8");
    expect(buttonSource).toContain("isRootNavPage");
    expect(buttonSource).toContain("return null");
  });

  it("shows destination name derived from previous path, not a hardcoded generic label", () => {
    const buttonSource = readFileSync("src/components/navigation/back-navigation-button.tsx", "utf-8");
    // label must come from getBackNavigationTarget(previousPath).label, not a literal string
    expect(buttonSource).toContain("getBackNavigationTarget(previousPath)");
    expect(buttonSource).not.toContain('"Previous page"');
    expect(buttonSource).not.toContain("Fallback:");
  });

  it("pops the destination from history before navigating back to prevent two-page bounce", () => {
    const buttonSource = readFileSync("src/components/navigation/back-navigation-button.tsx", "utf-8");
    // The onClick handler must trim history before calling router.push so that
    // when the destination page's useEffect fires it does not re-insert the
    // originating page as the new "previous", which caused infinite A↔B bouncing.
    expect(buttonSource).toContain(".slice(0, -1)");
    expect(buttonSource).toContain("writeNavigationHistory(trimmed)");
  });
});
