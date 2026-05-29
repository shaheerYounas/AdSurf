import { chromium } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function fullWorkflowTest() {
  const browser = await chromium.launch({ headless: false, slowMo: 800 });
  const context = await browser.newContext();
  const page = await context.newPage();

  const issues = [];
  let stepsPassed = 0;

  try {
    console.log('🚀 FULL WORKFLOW TEST - Complete 20/20 Compliance Check\n');

    // STEP 1: Upload file
    console.log('STEP 1: Upload report file');
    await page.goto('http://localhost:3000/agents', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'screenshots/workflow-01-initial.png', fullPage: true });

    const fileInput = page.locator('input[type="file"]').first();
    const filePath = path.resolve(__dirname, 'Sponsored_Products_Search_term_report (2).xlsx');
    await fileInput.setInputFiles(filePath);
    console.log('  ✓ File selected');

    const uploadBtn = page.locator('button:has-text("Upload"), button:has-text("upload")').first();
    await uploadBtn.click();
    console.log('  ✓ Upload button clicked');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'screenshots/workflow-02-upload-clicked.png', fullPage: true });
    stepsPassed++;

    // STEP 2: Wait for upload to complete
    console.log('\nSTEP 2: Wait for upload to complete');
    let uploadComplete = false;
    for (let i = 0; i < 30; i++) {
      const bodyText = await page.textContent('body');

      // Check if upload is complete (not showing "Uploading..." anymore)
      if (!bodyText.includes('Uploading report...') &&
          (bodyText.includes('success') || bodyText.includes('uploaded') || bodyText.includes('completed'))) {
        uploadComplete = true;
        console.log('  ✓ Upload completed');
        break;
      }

      if (i % 5 === 0) {
        console.log(`  Waiting... ${i}s`);
      }
      await page.waitForTimeout(1000);
    }

    if (!uploadComplete) {
      console.log('  ⚠️  Upload still showing "Uploading report..." after 30s');
      issues.push('Upload appears stuck in "Uploading report..." state');
      await page.screenshot({ path: 'screenshots/workflow-03-upload-stuck.png', fullPage: true });
    } else {
      await page.screenshot({ path: 'screenshots/workflow-03-upload-complete.png', fullPage: true });
      stepsPassed++;
    }

    // STEP 3: Run analysis
    console.log('\nSTEP 3: Run analysis');
    const runAnalysisBtn = page.locator('button:has-text("Run analysis")').first();
    const analysisVisible = await runAnalysisBtn.isVisible({ timeout: 3000 }).catch(() => false);

    if (analysisVisible) {
      console.log('  ✓ "Run analysis" button found');
      await runAnalysisBtn.click();
      console.log('  ✓ Analysis started');
      await page.waitForTimeout(5000);
      await page.screenshot({ path: 'screenshots/workflow-04-analysis-started.png', fullPage: true });
      stepsPassed++;
    } else {
      console.log('  ✗ "Run analysis" button not found');
      issues.push('"Run analysis" button not visible');
    }

    // STEP 4: Wait for agents to run
    console.log('\nSTEP 4: Wait for agent workflow to process');
    let workflowComplete = false;
    for (let i = 0; i < 60; i++) {
      const bodyText = await page.textContent('body');

      // Look for completion indicators
      if (bodyText.includes('completed') || bodyText.includes('succeeded') ||
          bodyText.includes('Compliance') || bodyText.includes('20/20')) {
        workflowComplete = true;
        console.log('  ✓ Workflow processing detected');
        break;
      }

      if (i % 10 === 0) {
        console.log(`  Waiting for agents... ${i}s`);
        await page.screenshot({ path: `screenshots/workflow-05-processing-${i}s.png`, fullPage: true });
      }
      await page.waitForTimeout(1000);
    }

    if (workflowComplete) {
      console.log('  ✓ Workflow completed');
      stepsPassed++;
    } else {
      console.log('  ⚠️  Workflow still processing after 60s');
      issues.push('Workflow did not complete within 60s');
    }

    await page.screenshot({ path: 'screenshots/workflow-06-final-state.png', fullPage: true });

    // STEP 5: Check for detection results
    console.log('\nSTEP 5: Verify report detection results');
    const bodyText = await page.textContent('body');

    const detectionChecks = {
      'Report type detected': bodyText.includes('Sponsored Products') || bodyText.includes('Search Term'),
      'Confidence level shown': bodyText.includes('HIGH') || bodyText.includes('confidence'),
      'Required columns check': bodyText.includes('required_columns_present') || bodyText.includes('required'),
      'Missing columns info': bodyText.includes('missing_columns') || bodyText.includes('missing'),
    };

    console.log('  Detection Results:');
    for (const [check, passed] of Object.entries(detectionChecks)) {
      console.log(`    ${passed ? '✓' : '✗'} ${check}`);
      if (passed) stepsPassed++;
      else issues.push(`Detection check failed: ${check}`);
    }

    // STEP 6: Look for next workflow steps
    console.log('\nSTEP 6: Check for next workflow steps');
    const nextStepButtons = await page.locator('button:has-text("Continue"), button:has-text("Next"), button:has-text("Mapping"), button:has-text("Campaign"), a:has-text("View")').all();

    if (nextStepButtons.length > 0) {
      console.log(`  ✓ Found ${nextStepButtons.length} next-step options`);
      stepsPassed++;
    } else {
      console.log('  ✗ No next-step buttons found');
      issues.push('No navigation to next workflow step');
    }

    // STEP 7: Check for errors
    console.log('\nSTEP 7: Check for errors');
    const errorElements = await page.locator('[class*="error"]:visible, [role="alert"]:visible, .text-red-500:visible').all();

    if (errorElements.length > 0) {
      console.log(`  ⚠️  Found ${errorElements.length} error elements:`);
      for (const el of errorElements) {
        const text = await el.textContent();
        if (text && text.trim()) {
          console.log(`    - ${text.trim()}`);
          issues.push(`Error: ${text.trim()}`);
        }
      }
    } else {
      console.log('  ✓ No errors found');
      stepsPassed++;
    }

    // FINAL SUMMARY
    console.log('\n' + '='.repeat(80));
    console.log('WORKFLOW TEST SUMMARY');
    console.log('='.repeat(80));
    console.log(`\nSteps Passed: ${stepsPassed}`);
    console.log(`Issues Found: ${issues.length}`);

    if (issues.length > 0) {
      console.log('\n❌ ISSUES IDENTIFIED:');
      issues.forEach((issue, i) => {
        console.log(`  ${i + 1}. ${issue}`);
      });
    } else {
      console.log('\n✅ ALL CHECKS PASSED!');
    }

    console.log('\n📸 Screenshots saved to screenshots/ directory');
    console.log('='.repeat(80));

  } catch (error) {
    console.error('\n❌ FATAL ERROR:', error.message);
    console.error(error.stack);
    await page.screenshot({ path: 'screenshots/workflow-error.png', fullPage: true });
    issues.push(`Fatal error: ${error.message}`);
  } finally {
    await browser.close();

    // Write issues to file
    if (issues.length > 0) {
      const fs = await import('fs');
      fs.writeFileSync('ISSUES_FOUND.txt', issues.join('\n'));
      console.log('\n📝 Issues written to ISSUES_FOUND.txt');
    }
  }
}

fullWorkflowTest();
