import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = path.dirname(fileURLToPath(import.meta.url));

test("bulk product import requires review before creating products", async ({ page }, testInfo) => {
  const fixturePath = path.resolve(currentDir, "../../../tests/fixtures/bulk-products-valid.csv");
  const token = Date.now().toString(36).slice(-5).toUpperCase();
  const csv = (await fs.readFile(fixturePath, "utf-8"))
    .replaceAll("B0GARL1234", `B0E2A${token}`)
    .replaceAll("B0SPAT1234", `B0E2B${token}`)
    .replaceAll("B0DRAW1234", `B0E2C${token}`)
    .replaceAll("GARLIC-PRESS-01", `GARLIC-E2E-${token}`)
    .replaceAll("SPATULA-SET-02", `SPATULA-E2E-${token}`)
    .replaceAll("DRAWER-ORG-03", `DRAWER-E2E-${token}`);
  const uploadPath = path.join(testInfo.outputDir, "bulk-products-e2e.csv");
  await fs.mkdir(testInfo.outputDir, { recursive: true });
  await fs.writeFile(uploadPath, csv, "utf-8");

  await page.addInitScript(() => {
    window.localStorage.setItem("adsurf-onboarding-completed", "1");
  });
  await page.goto("/products/bulk");
  await page.locator('input[type="file"]').setInputFiles(uploadPath);
  await page.getByRole("button", { name: /Upload and validate/i }).click();

  await expect(page.getByText(/Columns detected in/i)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Product Name")).toBeVisible();
  await page.getByRole("button", { name: /Continue/i }).click();

  await expect(page.getByText("To create", { exact: true })).toBeVisible();
  await expect(page.getByText("New product profiles")).toBeVisible();
  await page.getByRole("button", { name: /Apply 3 valid rows/i }).click();

  await expect(page.getByText(/3 products created/i)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Failed")).toBeVisible();
});
