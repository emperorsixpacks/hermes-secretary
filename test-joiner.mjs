/**
 * Quick test to verify the Google Meet Playwright joiner works.
 * Run with: npx ts-node --esm test-joiner.mjs OR node --loader ts-node/esm test-joiner.mjs
 *
 * Or compile first: npx tsc test-joiner.mjs --module esnode && node test-joiner.js
 */

import { SecretaryPlugin } from './src/index.js';

const MEET_CODE = process.argv[2] || 'test-demo-123';

console.log(`\n=== Secretary Joiner Test ===\n`);
console.log(`Meeting code: ${MEET_CODE}\n`);
console.log('⚠️  This will launch a browser window. Make sure you\'re signed into Google.\n');

// Run the test
(async () => {
  const plugin = new SecretaryPlugin();

  try {
    // Step 1: Initialize browser with persistent profile
    console.log('1. Initializing browser...');
    await plugin.init();
    console.log('   ✓ Browser launched\n');

    // Step 2: Join the Meet
    console.log(`2. Joining Meet code: ${MEET_CODE}...`);
    await plugin.joinMeet(MEET_CODE);
    console.log('   ✓ Join handled\n');

    // Step 3: Wait a moment for captions to appear
    console.log('3. Waiting for captions to appear...');
    await plugin.page?.waitForTimeout(3000);

    // Step 4: Scrape captions
    console.log('4. Scraping captions...');
    const captions = await plugin.scrapeCaptions();
    console.log(`   📝 Captions captured: ${captions.length}`);

    if (captions.length > 0) {
      console.log('   📄 First few captions:');
      captions.slice(0, 3).forEach((c, i) => {
        console.log(`     ${i + 1}. ${c.substring(0, 100)}${c.length > 100 ? '...' : ''}`);
      });
    } else {
      console.log('   (No captions found - this is okay if no one is speaking or captions are off)');
    }

    console.log('\n✅ Test completed successfully!\n');

  } catch (error) {
    console.error('\n❌ Test failed:', error);
    console.error('   This could be due to:');
    console.error('   - Invalid meeting code');
    console.error('   - Google Meet join screen changed');
    console.error('   - Network issues');
    process.exit(1);
  } finally {
    // Step 5: Clean up
    console.log('5. Closing browser...');
    await plugin.close();
    console.log('   ✓ Browser closed\n');
  }
})();