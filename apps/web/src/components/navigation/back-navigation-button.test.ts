import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("global previous-page control", () => {
  it("is mounted from the root layout and uses deterministic fallback navigation", () => {
    const layoutSource = readFileSync("src/app/layout.tsx", "utf-8");
    const buttonSource = readFileSync("src/components/navigation/back-navigation-button.tsx", "utf-8");

    expect(layoutSource).toContain("BackNavigationButton");
    expect(buttonSource).toContain("Previous page");
    expect(buttonSource).toContain("getBackNavigationTarget");
    expect(buttonSource).toContain("sessionStorage");
  });
});
