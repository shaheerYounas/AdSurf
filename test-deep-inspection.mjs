import { chromium } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function deepInspectionTest() {
  const browser = await chromium.launch({ headless: false, slowMo: 500 });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    console.log('🔍 DEEP INSPECTION TEST - Finding all workflow issues\n');

    // Step 1: Navigate and upload
    console.log('Step 1: Navigate to agents page and upload file');
    await page.goto('http://localhost:3000/agents', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);

    const fileInput = page.locator('input[type="file"]').first();
    const filePath = path.resolve(__dirname, 'Sponsored_Products_Search_term_report (2).xlsx');
    await fileInput.setInputFiles(filePath);
    console.log('  ✓ File selected');

    const uploadBtn = page.locator('button:has-text("Upload"), button:has-text("upload")').first();
    await uploadBtn.click();
    console.log('  ✓ Upload clicked');

    // Step 2: Wait and capture page state
    console.log('\nStep 2: Waiting for processing (30s)...');
    await page.waitForTimeout(30000);

    // Extract all text content
    const bodyText = await page.textContent('body');
    console.log('\n📄 PAGE CONTENT ANALYSIS:');
    console.log('  Total page text length:', bodyText.length);

    // Look for key indicators
    const indicators = {
      'Report uploaded': bodyText.includes('uploaded') || bodyText.includes('Upload'),
      'Detection result': bodyText.includes('detected') || bodyText.includes('Detection'),
      'Confidence level': bodyText.includes('confidence') || bodyText.includes('HIGH') || bodyText.includes('MEDIUM'),
      'Required columns': bodyText.includes('required') || bodyText.includes('columns'),
      'Missing columns': bodyText.includes('missing'),
      'Workflow status': bodyText.includes('running') || bodyText.includes('completed') || bodyText.includes('succeeded'),
      'Agent names': bodyText.includes('agent') || bodyText.includes('Agent'),
      'Error messages': bodyText.includes('error') || bodyText.includes('Error') || bodyText.includes('failed'),
    };

    console.log('\n  Key Indicators:');
    for (const [key, found] of Object.entries(indicators)) {
      console.log(`    ${found ? '✓' : '✗'} ${key}`);
    }

    // Extract specific sections
    console.log('\n📊 EXTRACTING SPECIFIC DATA:');

    // Look for status messages
    const statusElements = await page.locator('[class*="status"], [class*="message"], [class*="alert"]').all();
    if (statusElements.length > 0) {
      console.log(`\n  Status Messages (${statusElements.length} found):`);
      for (let i = 0; i < Math.min(statusElements.length, 5); i++) {
        const text = await statusElements[i].textContent();
        if (text && text.trim()) {
          console.log(`    ${i + 1}. ${text.trim().substring(0, 100)}`);
        }
      }
    }

    // Look for buttons/actions available
    const buttons = await page.locator('button:visible').all();
    console.log(`\n  Available Buttons (${buttons.length} found):`);
    for (let i = 0; i < Math.min(buttons.length, 10); i++) {
      const text = await buttons[i].textContent();
      if (text && text.trim()) {
        console.log(`    ${i + 1}. "${text.trim()}"`);
      }
    }

    // Look for links
    const links = await page.locator('a:visible').all();
    console.log(`\n  Available Links (${links.length} found):`);
    for (let i = 0; i < Math.min(links.length, 10); i++) {
      const text = await links[i].textContent();
      const href = await links[i].getAttribute('href');
      if (text && text.trim()) {
        console.log(`    ${i + 1}. "${text.trim()}" → ${href}`);
      }
    }

    // Check for workflow visualization
    console.log('\n🔄 WORKFLOW STATE:');
    const workflowElements = await page.locator('[class*="workflow"], [class*="node"], [class*="timeline"], [class*="progress"]').all();
    console.log(`  Workflow elements found: ${workflowElements.length}`);

    // Look for agent status
    const agentElements = await page.locator('[class*="agent"]').all();
    console.log(`  Agent elements found: ${agentElements.length}`);

    if (agentElements.length > 0) {
      console.log('\n  Agent Details:');
      for (let i = 0; i < Math.min(agentElements.length, 5); i++) {
        const text = await agentElements[i].textContent();
        if (text && text.trim()) {
          console.log(`    ${i + 1}. ${text.trim().substring(0, 150)}`);
        }
      }
    }

    // Take detailed screenshot
    await page.screenshot({ path: 'screenshots/deep-inspection-full.png', fullPage: true });

    // Check current URL
    console.log('\n🌐 CURRENT STATE:');
    console.log('  URL:', page.url());
    console.log('  Title:', await page.title());

    // Look for any JSON data in the page
    const preElements = await page.locator('pre, code').all();
    if (preElements.length > 0) {
      console.log(`\n  JSON/Code blocks found: ${preElements.length}`);
      for (let i = 0; i < Math.min(preElements.length, 3); i++) {
        const text = await preElements[i].textContent();
        if (text && text.trim() && text.includes('{')) {
          console.log(`\n  Block ${i + 1}:`);
          console.log(text.substring(0, 500));
        }
      }
    }

    // Check for specific compliance indicators
    console.log('\n✅ COMPLIANCE INDICATORS:');
    const complianceChecks = {
      'File uploaded successfully': bodyText.toLowerCase().includes('success') || bodyText.toLowerCase().includes('uploaded'),
      'Report type detected': bodyText.includes('Sponsored Products') || bodyText.includes('Search Term'),
      'Columns analyzed': bodyText.includes('column') || bodyText.includes('Column'),
      'Workflow started': bodyText.includes('running') || bodyText.includes('started') || bodyText.includes('processing'),
      'Next step available': buttons.length > 2, // More than just basic nav buttons
    };

    for (const [check, passed] of Object.entries(complianceChecks)) {
      console.log(`  ${passed ? '✅' : '❌'} ${check}`);
    }

    // Try to find and click next step
    console.log('\n🎯 ATTEMPTING TO PROGRESS WORKFLOW:');
    const nextButtons = await page.locator('button:has-text("Continue"), button:has-text("Next"), button:has-text("Proceed"), a:has-text("View"), a:has-text("Open")').all();

    if (nextButtons.length > 0) {
      console.log(`  Found ${nextButtons.length} potential next-step buttons`);
      try {
        const btnText = await nextButtons[0].textContent();
        console.log(`  Clicking: "${btnText?.trim()}"`);
        await nextButtons[0].click();
        await page.waitForTimeout(3000);
        await page.screenshot({ path: 'screenshots/deep-inspection-next-page.png', fullPage: true });
        console.log('  ✓ Navigated to next page');
        console.log('  New URL:', page.url());
      } catch (e) {
        console.log(`  ✗ Failed to click: ${e.message}`);
      }
    } else {
      console.log('  ✗ No next-step buttons found');
    }

    console.log('\n' + '='.repeat(80));
    console.log('INSPECTION COMPLETE');
    console.log('='.repeat(80));

  } catch (error) {
    console.error('\n❌ ERROR:', error.message);
    await page.screenshot({ path: 'screenshots/deep-inspection-error.png', fullPage: true });
  } finally {
    await browser.close();
  }
}

deepInspectionTest();
