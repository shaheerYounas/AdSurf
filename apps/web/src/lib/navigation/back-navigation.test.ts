import { describe, expect, it } from "vitest";
import { getBackNavigationTarget, isInternalNavigationPath, normalizePathname } from "./back-navigation";

describe("back navigation route fallbacks", () => {
  it.each([
    ["/dashboard", "/dashboard", "Workspace home"],
    ["/products", "/dashboard", "Dashboard"],
    ["/products/new", "/products", "Products"],
    ["/products/prod-1", "/products", "Products"],
    ["/products/prod-1/uploads", "/products/prod-1", "Product profile"],
    ["/products/prod-1/uploads/upload-9/mapping", "/products/prod-1/uploads", "Uploads"],
    ["/products/prod-1/monitoring", "/products/prod-1", "Product profile"],
    ["/products/prod-1/monitoring/import-7/agents", "/products/prod-1/monitoring", "Monitoring"],
    ["/agents", "/dashboard", "Dashboard"],
    ["/agent-builder", "/agents", "Agents"],
    ["/recommendations", "/dashboard", "Dashboard"],
  ])("maps %s back to %s", (pathname, href, label) => {
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
