import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('File Upload and Compliance Testing', () => {
  test('upload Sponsored_Products_Search_term_report and verify 20/20 compliance', async ({ page }) => {
    // Navigate to the app
    await page.goto('http://localhost:3000');
    await page.waitForLoadState('networkidle');

    // Take initial screenshot
    await page.screenshot({ path: 'screenshots/01-homepage.png', fullPage: true });

    // Look for products or navigation to upload page
    // First, let's see what's on the page
    console.log('Page title:', await page.title());

    // Try to find product or upload links
    const productLinks = await page.locator('a[href*="/products"]').all();
    console.log(`Found ${productLinks.length} product links`);

    if (productLinks.length > 0) {
      // Click first product
      await productLinks[0].click();
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: 'screenshots/02-product-page.png', fullPage: true });
    }

    // Look for upload button or link
    const uploadLink = page.locator('a[href*="/uploads"], button:has-text("Upload")').first();
    if (await uploadLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await uploadLink.click();
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: 'screenshots/03-upload-page.png', fullPage: true });
    }

    // Find file input
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeVisible({ timeout: 10000 });

    // Upload the file
    const filePath = path.resolve('Sponsored_Products_Search_term_report (2).xlsx');
    await fileInput.setInputFiles(filePath);
    console.log('File selected:', filePath);

    await page.screenshot({ path: 'screenshots/04-file-selected.png', fullPage: true });

    // Find and click submit/upload button
    const submitButton = page.locator('button:has-text("Upload"), button:has-text("Submit"), button[type="submit"]').first();
    await expect(submitButton).toBeVisible();
    await submitButton.click();
    console.log('Upload initiated');

    await page.screenshot({ path: 'screenshots/05-upload-initiated.png', fullPage: true });

    // Wait for upload to complete and processing to start
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'screenshots/06-processing.png', fullPage: true });

    // Look for compliance status
    // Wait for compliance status to appear (may take some time)
    const compliancePattern = /compliance.*status.*20.*20|20.*\/.*20/i;

    let complianceFound = false;
    let attempts = 0;
    const maxAttempts = 30; // 30 seconds

    while (!complianceFound && attempts < maxAttempts) {
      const pageText = await page.textContent('body');
      if (pageText && compliancePattern.test(pageText)) {
        complianceFound = true;
        console.log('Compliance status 20/20 found!');
        break;
      }

      // Check for any compliance indicators
      const complianceElements = await page.locator('*:has-text("Compliance"), *:has-text("compliance"), *:has-text("20/20")').all();
      if (complianceElements.length > 0) {
        console.log(`Found ${complianceElements.length} compliance-related elements`);
        for (const el of complianceElements) {
          const text = await el.textContent();
          console.log('Compliance element text:', text);
        }
      }

      await page.waitForTimeout(1000);
      attempts++;

      if (attempts % 5 === 0) {
        await page.screenshot({ path: `screenshots/07-waiting-${attempts}s.png`, fullPage: true });
      }
    }

    // Take final screenshot
    await page.screenshot({ path: 'screenshots/08-final-state.png', fullPage: true });

    // Check for any error messages
    const errorElements = await page.locator('[class*="error"], [role="alert"], .text-red-500, .text-destructive').all();
    if (errorElements.length > 0) {
      console.log('Errors found:');
      for (const el of errorElements) {
        const text = await el.textContent();
        console.log('  -', text);
      }
    }

    // Verify compliance status
    if (complianceFound) {
      console.log('✅ SUCCESS: Compliance status 20/20 achieved');
    } else {
      console.log('❌ FAIL: Compliance status 20/20 not found after 30 seconds');
      throw new Error('Compliance status 20/20 not achieved');
    }
  });
});
