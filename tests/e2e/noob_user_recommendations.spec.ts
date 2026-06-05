import { test, expect } from '@playwright/test';

test('noob user recommendations flow', async ({ page }) => {
  await page.goto('/');
  await page.click('text="Recommendations"');
  await expect(page.locator('h1', { hasText: 'Approval Queue' })).toBeVisible({ timeout: 10000 });

  // Try to approve if any exist
  const approveBtn = page.locator('button', { hasText: 'Approve' }).first();
  if (await approveBtn.isVisible()) {
    await approveBtn.click();
    await expect(page.locator('textarea')).toBeVisible();
    await expect(page.locator('button:has-text("Confirm approve")')).toBeDisabled();
    await page.fill('textarea', 'QA confirms the modal requires a note but does not record a decision.');
    await expect(page.locator('button:has-text("Confirm approve")')).toBeEnabled();
    await page.click('button:has-text("Cancel")');
  }
});
