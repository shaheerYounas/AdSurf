import { chromium } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function runTest() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    console.log('Navigating to http://localhost:3000...');
    await page.goto('http://localhost:3000');
    await page.waitForLoadState('networkidle');

    await page.screenshot({ path: 'screenshots/01-homepage.png', fullPage: true });
    console.log('✓ Screenshot: homepage');

    // Look for products link
    const productLinks = await page.locator('a[href*="/products"]').all();
    console.log(`Found ${productLinks.length} product links`);

    if (productLinks.length > 0) {
      console.log('Clicking first product link...');
      await productLinks[0].click();
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: 'screenshots/02-product-page.png', fullPage: true });
      console.log('✓ Screenshot: product page');
    }

    // Look for uploads link
    const uploadsLink = page.locator('a[href*="/uploads"]').first();
    const isVisible = await uploadsLink.isVisible({ timeout: 5000 }).catch(() => false);

    if (isVisible) {
      console.log('Clicking uploads link...');
      await uploadsLink.click();
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: 'screenshots/03-upload-page.png', fullPage: true });
      console.log('✓ Screenshot: upload page');
    }

    // Find file input
    console.log('Looking for file input...');
    const fileInput = page.locator('input[type="file"]');
    await fileInput.waitFor({ state: 'visible', timeout: 10000 });

    // Upload the file
    const filePath = path.resolve(__dirname, 'Sponsored_Products_Search_term_report (2).xlsx');
    console.log('Uploading file:', filePath);
    await fileInput.setInputFiles(filePath);

    await page.screenshot({ path: 'screenshots/04-file-selected.png', fullPage: true });
    console.log('✓ Screenshot: file selected');

    // Find and click submit button
    console.log('Looking for submit button...');
    const submitButton = page.locator('button:has-text("Upload"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.waitFor({ state: 'visible', timeout: 5000 });
    await submitButton.click();
    console.log('✓ Upload button clicked');

    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'screenshots/05-upload-initiated.png', fullPage: true });
    console.log('✓ Screenshot: upload initiated');

    // Wait for processing and look for compliance status
    console.log('Waiting for compliance status...');
    let complianceFound = false;
    let attempts = 0;
    const maxAttempts = 60; // 60 seconds

    while (!complianceFound && attempts < maxAttempts) {
      const pageText = await page.textContent('body');

      // Look for compliance patterns
      if (pageText.includes('20/20') || pageText.includes('Compliance Status: 20/20')) {
        complianceFound = true;
        console.log('✅ SUCCESS: Compliance status 20/20 found!');
        break;
      }

      // Check for compliance-related elements
      const complianceElements = await page.locator('text=/compliance/i, text=/20\\/20/').all();
      if (complianceElements.length > 0) {
        for (const el of complianceElements) {
          const text = await el.textContent();
          console.log('  Compliance element:', text);
          if (text && text.includes('20/20')) {
            complianceFound = true;
            break;
          }
        }
      }

      await page.waitForTimeout(1000);
      attempts++;

      if (attempts % 5 === 0) {
        console.log(`  Waiting... ${attempts}s elapsed`);
        await page.screenshot({ path: `screenshots/06-waiting-${attempts}s.png`, fullPage: true });
      }
    }

    // Take final screenshot
    await page.screenshot({ path: 'screenshots/07-final-state.png', fullPage: true });
    console.log('✓ Screenshot: final state');

    // Check for errors
    const errorElements = await page.locator('[class*="error"], [role="alert"], .text-red-500, .text-destructive').all();
    if (errorElements.length > 0) {
      console.log('\n⚠️  Errors found:');
      for (const el of errorElements) {
        const text = await el.textContent();
        if (text && text.trim()) {
          console.log('  -', text.trim());
        }
      }
    }

    if (!complianceFound) {
      console.log('\n❌ FAIL: Compliance status 20/20 not found after 60 seconds');
      console.log('Current page URL:', page.url());
      console.log('Check screenshots for details');
    }

  } catch (error) {
    console.error('❌ Test failed with error:', error.message);
    await page.screenshot({ path: 'screenshots/error.png', fullPage: true });
  } finally {
    await browser.close();
  }
}

runTest();
