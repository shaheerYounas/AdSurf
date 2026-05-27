import { test, expect } from '@playwright/test';

test('noob user recommendations flow', async ({ page }) => {
  await page.goto('/');
  await page.click('text="Recommendations"');
  await expect(page.locator('h1', { hasText: 'Approval Queue' })).toBeVisible({ timeout: 10000 });

  // Try to approve if any exist
  const approveBtn = page.locator('button', { hasText: 'Approve' }).first();
  if (await approveBtn.isVisible()) {
    await approveBtn.click();
    // note is required?
    await page.fill('textarea', 'LGTM');
    await page.click('button:has-text("Confirm Approval")');
    await expect(page.locator('text=Status: Approved').first()).toBeVisible();
  }
});
