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
    console.log('Navigating to http://localhost:3000/agents...');
    await page.goto('http://localhost:3000/agents');
    await page.waitForLoadState('networkidle');

    await page.screenshot({ path: 'screenshots/10-agents-page.png', fullPage: true });
    console.log('✓ Screenshot: agents page');

    // Look for file input on agents page
    const fileInput = page.locator('input[type="file"]').first();
    const isVisible = await fileInput.isVisible({ timeout: 5000 }).catch(() => false);

    if (isVisible) {
      console.log('Found file input on agents page');

      // Upload the file
      const filePath = path.resolve(__dirname, 'Sponsored_Products_Search_term_report (2).xlsx');
      console.log('Uploading file:', filePath);
      await fileInput.setInputFiles(filePath);

      await page.screenshot({ path: 'screenshots/11-file-selected-agents.png', fullPage: true });
      console.log('✓ Screenshot: file selected');

      // Find and click upload button
      const uploadButton = page.locator('button:has-text("Upload"), button:has-text("1. Upload")').first();
      const uploadVisible = await uploadButton.isVisible({ timeout: 5000 }).catch(() => false);

      if (uploadVisible) {
        await uploadButton.click();
        console.log('✓ Upload button clicked');

        await page.waitForTimeout(3000);
        await page.screenshot({ path: 'screenshots/12-upload-processing.png', fullPage: true });

        // Wait for detection results
        console.log('Waiting for report detection...');
        let detectionFound = false;
        let attempts = 0;
        const maxAttempts = 60;

        while (!detectionFound && attempts < maxAttempts) {
          const pageText = await page.textContent('body');

          // Look for detection indicators
          if (pageText.includes('detected') ||
              pageText.includes('Detection') ||
              pageText.includes('required_columns_present') ||
              pageText.includes('HIGH') ||
              pageText.includes('confidence')) {
            console.log('✅ Detection result found!');
            detectionFound = true;

            // Look for specific detection details
            if (pageText.includes('required_columns_present')) {
              console.log('  Found: required_columns_present');
            }
            if (pageText.includes('missing_columns')) {
              console.log('  Found: missing_columns');
            }
            break;
          }

          await page.waitForTimeout(1000);
          attempts++;

          if (attempts % 5 === 0) {
            console.log(`  Waiting... ${attempts}s elapsed`);
            await page.screenshot({ path: `screenshots/13-waiting-${attempts}s.png`, fullPage: true });
          }
        }

        // Take final screenshot
        await page.screenshot({ path: 'screenshots/14-final-detection.png', fullPage: true });
        console.log('✓ Screenshot: final detection state');

        // Extract and display detection info
        const detectionElements = await page.locator('text=/detection|confidence|required|missing/i').all();
        if (detectionElements.length > 0) {
          console.log('\n📊 Detection Information:');
          for (const el of detectionElements) {
            const text = await el.textContent();
            if (text && text.trim()) {
              console.log('  ', text.trim());
            }
          }
        }

      } else {
        console.log('❌ Upload button not found');
      }
    } else {
      console.log('❌ File input not found on agents page');
    }

    // Check for any error messages
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

  } catch (error) {
    console.error('❌ Test failed with error:', error.message);
    await page.screenshot({ path: 'screenshots/error-agents.png', fullPage: true });
  } finally {
    await browser.close();
  }
}

runTest();
