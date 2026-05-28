import { expect, test } from "@playwright/test";

test("recommendations page keeps approval-only safety boundary visible", async ({ page }) => {
  await page.goto("/recommendations");

  await expect(page.getByText(/Recommendation only|Requires human approval|No live Amazon Ads/i).first()).toBeVisible();
  await expect(page.getByText(/Approval|recommendation/i).first()).toBeVisible();
});
