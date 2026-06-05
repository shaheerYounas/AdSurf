import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("adsurf-onboarding-completed", "true"));
});

test("agent control center exposes controls, workflow, timeline, and approval boundary", async ({ page }) => {
  await page.goto("/agents");

  await expect(page.getByRole("heading", { name: "Agent Control Center" }).last()).toBeVisible();
  await expect(page.getByText("Visual Canvas")).toBeVisible();
  await expect(page.getByText("AGENT PIPELINE")).toBeVisible();
  await expect(page.locator("body")).toContainText(/Recommendation only|Requires human approval|No live Amazon Ads/i);

  await page.getByRole("button", { name: /Run analysis/i }).click();
  await expect(page.getByText(/Upload a report|open an import-level workflow/i)).toBeVisible();
});
