import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const dirname = path.dirname(fileURLToPath(import.meta.url));

test("noob user can upload an account report or sees a clear error", async ({ page }) => {
  await page.goto("/agents");
  await page.getByLabel("Report file").setInputFiles(path.resolve(dirname, "../../../tests/fixtures/amazon_ads_search_term_report.csv"));

  const uploadButton = page.getByRole("button", { name: /upload report/i });
  await expect(uploadButton).toBeEnabled();
  await uploadButton.click();

  await expect(page.locator("#reports").getByText(/Creating upload record|Storing report file|Report uploaded|could not|Check API health/i).first()).toBeVisible({ timeout: 15000 });
});
