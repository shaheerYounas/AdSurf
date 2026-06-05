import { describe, expect, it } from "vitest";
import { getBackNavigationTarget, isInternalNavigationPath, isRootNavPage, normalizePathname } from "./back-navigation";

describe("back navigation route fallbacks", () => {
  it.each([
    ["/dashboard", "/dashboard", "Dashboard"],
    ["/products", "/dashboard", "Dashboard"],
    ["/products/new", "/products", "Products"],
    ["/products/prod-1", "/products", "Products"],
    ["/products/prod-1/uploads", "/products/prod-1", "Product"],
    ["/products/prod-1/monitoring", "/products/prod-1", "Product"],
    ["/products/prod-1/competitors", "/products/prod-1", "Product"],
    ["/products/prod-1/uploads/upload-9/mapping", "/products/prod-1/uploads", "Uploads"],
    ["/products/prod-1/monitoring/import-7/agents", "/products/prod-1/monitoring", "Monitoring"],
    ["/agents", "/dashboard", "Dashboard"],
    ["/agent-builder", "/agents", "Agents"],
    ["/recommendations", "/dashboard", "Dashboard"],
    ["/reports", "/dashboard", "Dashboard"],
  ])("maps %s → href=%s label=%s", (pathname, href, label) => {
    expect(getBackNavigationTarget(pathname)).toEqual({ href, label });
  });

  it("normalizes query strings, hashes, trailing slashes, and unsafe empty input", () => {
    expect(normalizePathname("/products/prod-1/uploads/?tab=files#top")).toBe("/products/prod-1/uploads");
    expect(normalizePathname(null)).toBe("/dashboard");
    expect(normalizePathname("https://example.com/products")).toBe("/dashboard");
  });

  it("accepts only internal app paths for stored history", () => {
    expect(isInternalNavigationPath("/products")).toBe(true);
    expect(isInternalNavigationPath("//example.com/products")).toBe(false);
    expect(isInternalNavigationPath("https://example.com/products")).toBe(false);
    expect(isInternalNavigationPath(null)).toBe(false);
  });
});

describe("isRootNavPage", () => {
  it("identifies top-level sidebar pages as root", () => {
    for (const path of ["/", "/dashboard", "/products", "/products/new", "/agents", "/agent-builder", "/recommendations", "/reports"]) {
      expect(isRootNavPage(path)).toBe(true);
    }
  });

  it("does not treat product sub-pages as root", () => {
    expect(isRootNavPage("/products/prod-1")).toBe(false);
    expect(isRootNavPage("/products/prod-1/monitoring")).toBe(false);
    expect(isRootNavPage("/products/prod-1/uploads")).toBe(false);
    expect(isRootNavPage("/products/prod-1/monitoring/import-7/agents")).toBe(false);
  });
});

describe("back button label derivation", () => {
  it("derives the correct destination label from the previous path", () => {
    // mirrors what BackNavigationButton does: getBackNavigationTarget(previousPath).label
    expect(getBackNavigationTarget("/products/prod-1").label).toBe("Products");
    expect(getBackNavigationTarget("/products/prod-1/monitoring").label).toBe("Product");
    expect(getBackNavigationTarget("/products/prod-1/monitoring/imp-1/agents").label).toBe("Monitoring");
    expect(getBackNavigationTarget("/products/prod-1/uploads/up-1/mapping").label).toBe("Uploads");
  });
});
