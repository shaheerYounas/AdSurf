import { chromium } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function runComplianceTest() {
  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = {
    phase1: {},
    phase2: {},
    phase3: {},
    issues: []
  };

  try {
    console.log('='.repeat(80));
    console.log('20/20 COMPLIANCE TEST - Based on gap-analysis-marketing-plan.md');
    console.log('='.repeat(80));

    // PHASE 1: Data Collection & Processing
    console.log('\n📊 PHASE 1: AUTOMATED MARKET RESEARCH & DATA PROCESSING\n');

    console.log('[1/20] Testing: Upload CSV/XLSX file...');
    await page.goto('http://localhost:3000/agents', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'screenshots/compliance-01-agents-page.png', fullPage: true });

    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      const filePath = path.resolve(__dirname, 'Sponsored_Products_Search_term_report (2).xlsx');
      await fileInput.setInputFiles(filePath);
      console.log('  ✅ [1/20] File upload: PASS');
      results.phase1['upload'] = 'PASS';
      await page.waitForTimeout(1000);
    } else {
      console.log('  ❌ [1/20] File upload: FAIL - No file input found');
      results.phase1['upload'] = 'FAIL';
      results.issues.push('No file input found on agents page');
    }

    console.log('[2/20] Testing: Upload button and processing...');
    const uploadBtn = page.locator('button:has-text("Upload"), button:has-text("upload")').first();
    if (await uploadBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await uploadBtn.click();
      console.log('  ✅ Upload initiated');
      await page.waitForTimeout(5000);
      await page.screenshot({ path: 'screenshots/compliance-02-after-upload.png', fullPage: true });
    } else {
      console.log('  ❌ [2/20] Upload button not found');
      results.issues.push('Upload button not visible');
    }

    // Wait for processing and check for detection results
    console.log('[3/20] Testing: Report detection and column analysis...');
    let detectionFound = false;
    for (let i = 0; i < 20; i++) {
      const bodyText = await page.textContent('body');
      if (bodyText.includes('detected') || bodyText.includes('confidence') || bodyText.includes('Sponsored Products')) {
        detectionFound = true;
        console.log('  ✅ [3/20] Report detection: PASS');
        results.phase1['detection'] = 'PASS';
        break;
      }
      await page.waitForTimeout(2000);
    }

    if (!detectionFound) {
      console.log('  ⚠️  [3/20] Report detection: TIMEOUT - Check screenshots');
      results.phase1['detection'] = 'TIMEOUT';
      results.issues.push('Report detection not visible after 40s');
    }

    await page.screenshot({ path: 'screenshots/compliance-03-detection-state.png', fullPage: true });

    // Check for workflow progression
    console.log('[4/20] Testing: Workflow progression to next steps...');
    const workflowNodes = await page.locator('[class*="workflow"], [class*="node"], [class*="agent"]').all();
    console.log(`  Found ${workflowNodes.length} workflow elements`);

    if (workflowNodes.length > 0) {
      console.log('  ✅ [4/20] Workflow UI: PASS');
      results.phase1['workflow'] = 'PASS';
    } else {
      console.log('  ⚠️  [4/20] Workflow UI: No workflow nodes found');
      results.phase1['workflow'] = 'PARTIAL';
    }

    // Look for next steps or buttons to continue
    console.log('[5/20] Testing: Navigation to scoring/mapping...');
    const continueButtons = await page.locator('button:has-text("Continue"), button:has-text("Next"), button:has-text("Map"), button:has-text("Score"), a:has-text("mapping")').all();

    if (continueButtons.length > 0) {
      console.log(`  Found ${continueButtons.length} navigation options`);
      // Try clicking the first one
      try {
        await continueButtons[0].click();
        await page.waitForTimeout(3000);
        await page.screenshot({ path: 'screenshots/compliance-04-next-step.png', fullPage: true });
        console.log('  ✅ [5/20] Navigation: PASS');
        results.phase1['navigation'] = 'PASS';
      } catch (e) {
        console.log('  ⚠️  [5/20] Navigation: Button not clickable');
        results.phase1['navigation'] = 'PARTIAL';
      }
    } else {
      console.log('  ⚠️  [5/20] Navigation: No continue buttons found');
      results.phase1['navigation'] = 'FAIL';
      results.issues.push('No navigation to next workflow step');
    }

    // PHASE 2: Campaign Creation (check if we can get there)
    console.log('\n🎯 PHASE 2: AUTOMATED CAMPAIGN CREATION\n');

    console.log('[6/20] Testing: Campaign generation availability...');
    const campaignLinks = await page.locator('a[href*="campaign"], button:has-text("Campaign"), button:has-text("Generate")').all();

    if (campaignLinks.length > 0) {
      console.log('  ✅ [6/20] Campaign features: FOUND');
      results.phase2['campaign_access'] = 'PASS';
    } else {
      console.log('  ⚠️  [6/20] Campaign features: Not accessible yet');
      results.phase2['campaign_access'] = 'BLOCKED';
      results.issues.push('Campaign generation not accessible from current state');
    }

    // PHASE 3: Monitoring (check if available)
    console.log('\n📈 PHASE 3: 14-DAY MONITORING SYSTEM\n');

    console.log('[7/20] Testing: Monitoring features availability...');
    const monitoringLinks = await page.locator('a[href*="monitoring"], a:has-text("Monitor"), button:has-text("Monitor")').all();

    if (monitoringLinks.length > 0) {
      console.log('  ✅ [7/20] Monitoring features: FOUND');
      results.phase3['monitoring_access'] = 'PASS';
    } else {
      console.log('  ⚠️  [7/20] Monitoring features: Not accessible');
      results.phase3['monitoring_access'] = 'BLOCKED';
    }

    // Take final screenshots
    await page.screenshot({ path: 'screenshots/compliance-final.png', fullPage: true });

    // Check for any errors
    console.log('\n🔍 CHECKING FOR ERRORS...\n');
    const errorElements = await page.locator('[class*="error"], [role="alert"], .text-red-500, .text-destructive').all();

    if (errorElements.length > 0) {
      console.log(`  ⚠️  Found ${errorElements.length} error elements:`);
      for (const el of errorElements) {
        const text = await el.textContent();
        if (text && text.trim()) {
          console.log(`    - ${text.trim()}`);
          results.issues.push(text.trim());
        }
      }
    } else {
      console.log('  ✅ No error messages found');
    }

    // Summary
    console.log('\n' + '='.repeat(80));
    console.log('COMPLIANCE TEST SUMMARY');
    console.log('='.repeat(80));

    const phase1Pass = Object.values(results.phase1).filter(v => v === 'PASS').length;
    const phase2Pass = Object.values(results.phase2).filter(v => v === 'PASS').length;
    const phase3Pass = Object.values(results.phase3).filter(v => v === 'PASS').length;

    console.log(`\nPhase 1 (Data Processing): ${phase1Pass}/${Object.keys(results.phase1).length} tests passed`);
    console.log(`Phase 2 (Campaign Creation): ${phase2Pass}/${Object.keys(results.phase2).length} tests passed`);
    console.log(`Phase 3 (Monitoring): ${phase3Pass}/${Object.keys(results.phase3).length} tests passed`);

    console.log(`\nTotal Issues Found: ${results.issues.length}`);
    if (results.issues.length > 0) {
      console.log('\nIssues:');
      results.issues.forEach((issue, i) => {
        console.log(`  ${i + 1}. ${issue}`);
      });
    }

    console.log('\n📸 Screenshots saved to screenshots/ directory');
    console.log('📄 Full report available in VERIFICATION_REPORT.md');
    console.log('='.repeat(80));

  } catch (error) {
    console.error('\n❌ TEST FAILED WITH ERROR:', error.message);
    await page.screenshot({ path: 'screenshots/compliance-error.png', fullPage: true });
    results.issues.push(`Fatal error: ${error.message}`);
  } finally {
    await browser.close();
    return results;
  }
}

runComplianceTest();
