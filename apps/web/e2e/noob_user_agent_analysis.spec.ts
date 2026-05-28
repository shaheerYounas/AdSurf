import { expect, test } from "@playwright/test";

test("agent control center exposes controls, workflow, timeline, and approval boundary", async ({ page }) => {
  await page.goto("/agents");

  await expect(page.getByRole("heading", { name: "Agent Control Center" }).last()).toBeVisible();
  await expect(page.getByText("Visual Workflow Canvas")).toBeVisible();
  await expect(page.getByText("Trace Timeline")).toBeVisible();
  await expect(page.getByText("Human Approval Checkpoints")).toBeVisible();
  await expect(page.getByText("Recommendation only").first()).toBeVisible();

  await page.getByRole("button", { name: /Run analysis/i }).click();
  await expect(page.getByText(/Upload a report|open an import-level workflow/i)).toBeVisible();
});
