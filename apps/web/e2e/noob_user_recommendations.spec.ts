import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("adsurf-onboarding-completed", "true"));
});

test("recommendations page keeps approval-only safety boundary visible", async ({ page }) => {
  await page.goto("/recommendations");

  await expect(page.locator("body")).toContainText(/Recommendation only|Requires human approval|No live Amazon Ads/i);
  await expect(page.getByText(/Approval|recommendation/i).first()).toBeVisible();
});
