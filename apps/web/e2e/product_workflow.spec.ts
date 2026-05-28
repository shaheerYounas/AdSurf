import { expect, test } from "@playwright/test";

test("product workflow entry points render for a beginner user", async ({ page }) => {
  await page.goto("/products/new");

  await expect(page.getByText(/Create|Product/i).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Products/i }).first()).toBeVisible();
});
