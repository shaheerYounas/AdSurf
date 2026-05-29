import { chromium } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function runTest() {
  const browser = await chromium.launch({ headless: false, slowMo: 500 });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    console.log('Step 1: Navigate to homepage');
    await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'screenshots/20-homepage.png', fullPage: true });

    const pageTitle = await page.title();
    console.log('  Page title:', pageTitle);

    // Check what links are available
    const links = await page.locator('a').all();
    console.log(`  Found ${links.length} links`);

    // Look for agents link
    const agentsLink = page.locator('a[href="/agents"], a:has-text("Agents"), a:has-text("Agent")').first();
    const agentsVisible = await agentsLink.isVisible({ timeout: 3000 }).catch(() => false);

    if (agentsVisible) {
      console.log('\nStep 2: Navigate to Agents page');
      await agentsLink.click();
      await page.waitForTimeout(3000);
      await page.screenshot({ path: 'screenshots/21-agents-page.png', fullPage: true });
      console.log('  ✓ On agents page');

      // Look for file upload
      console.log('\nStep 3: Look for file upload');
      const fileInput = page.locator('input[type="file"]').first();
      const fileInputVisible = await fileInput.isVisible({ timeout: 3000 }).catch(() => false);

      if (fileInputVisible) {
        console.log('  ✓ File input found');

        const filePath = path.resolve(__dirname, 'Sponsored_Products_Search_term_report (2).xlsx');
        console.log('  Uploading:', filePath);
        await fileInput.setInputFiles(filePath);
        await page.waitForTimeout(1000);
        await page.screenshot({ path: 'screenshots/22-file-selected.png', fullPage: true });
        console.log('  ✓ File selected');

        // Look for upload button
        console.log('\nStep 4: Click upload button');
        const uploadBtn = page.locator('button:has-text("Upload"), button:has-text("upload")').first();
        const uploadBtnVisible = await uploadBtn.isVisible({ timeout: 3000 }).catch(() => false);

        if (uploadBtnVisible) {
          await uploadBtn.click();
          console.log('  ✓ Upload button clicked');
          await page.waitForTimeout(5000);
          await page.screenshot({ path: 'screenshots/23-after-upload.png', fullPage: true });

          // Check page content for detection results
          console.log('\nStep 5: Check for detection results');
          const bodyText = await page.textContent('body');

          // Look for key indicators
          const indicators = [
            'required_columns_present',
            'missing_columns',
            'detected_report_type',
            'confidence',
            'HIGH',
            'MEDIUM',
            'LOW',
            'Sponsored Products',
            'Search Term'
          ];

          console.log('  Detection indicators found:');
          for (const indicator of indicators) {
            if (bodyText.includes(indicator)) {
              console.log(`    ✓ ${indicator}`);
            }
          }

          // Wait and take more screenshots
          for (let i = 1; i <= 6; i++) {
            await page.waitForTimeout(5000);
            await page.screenshot({ path: `screenshots/24-progress-${i * 5}s.png`, fullPage: true });
            console.log(`  Screenshot at ${i * 5}s`);
          }

        } else {
          console.log('  ❌ Upload button not found');
        }
      } else {
        console.log('  ❌ File input not found');
      }
    } else {
      console.log('  ❌ Agents link not found');

      // List available links
      console.log('\n  Available links:');
      for (let i = 0; i < Math.min(links.length, 10); i++) {
        const href = await links[i].getAttribute('href');
        const text = await links[i].textContent();
        console.log(`    - ${text?.trim()} (${href})`);
      }
    }

  } catch (error) {
    console.error('\n❌ Error:', error.message);
    await page.screenshot({ path: 'screenshots/error-final.png', fullPage: true });
  } finally {
    console.log('\nTest complete. Check screenshots/ directory for results.');
    await browser.close();
  }
}

runTest();
