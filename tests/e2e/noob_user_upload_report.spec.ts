import { test, expect } from '@playwright/test';
import path from 'path';

test('noob user upload report flow', async ({ page }) => {
  // 1. Open app
  await page.goto('/');

  // 2. Go to Agents
  await page.click('text="Agent Ops"'); // Or 'Agents' link

  // wait for Agents page
  await expect(page.locator('h1', { hasText: 'Agent Control Center' })).toBeVisible();

  // 3. Choose test CSV file
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(path.join(__dirname, '../fixtures/amazon_ads_search_term_report.csv'));

  // 4. Click Upload Report
  const uploadButton = page.locator('button', { hasText: 'Upload report' });
  await expect(uploadButton).toBeEnabled();
  
  await uploadButton.click();

  // 5. Expect loading state (Wait for spinner or message)
  // 6. Expect success message or created import
  await expect(page.locator('text=Report detected')).toBeVisible({ timeout: 10000 });
});
