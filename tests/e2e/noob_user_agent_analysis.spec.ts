import { test, expect } from '@playwright/test';

test('noob user agent analysis flow', async ({ page }) => {
  await page.goto('/');
  await page.click('text="Agent Ops"');
  await expect(page.locator('h1', { hasText: 'Agent Control Center' })).toBeVisible();

  // Assuming an import already exists or we trigger one manually
  const runAnalysisBtn = page.locator('button', { hasText: 'Run analysis' });
  if (await runAnalysisBtn.isVisible()) {
    await runAnalysisBtn.click();
    await expect(page.locator('text=running').first()).toBeVisible({ timeout: 15000 });
  }
});
