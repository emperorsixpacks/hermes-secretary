import { SecretaryPlugin, resolveSecretDir } from './src/index.ts';

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  if (i >= 0 && process.argv[i + 1]) return process.argv[i + 1];
  const pref = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(pref));
  return hit ? hit.slice(pref.length) : undefined;
}

const input = process.argv.find((a) => a && !a.startsWith('-') && !a.endsWith('join-meet.ts') && !a.includes('/node')) || arg('meet') || 'hfz-wssx-rpa';
const account = arg('account');
const meetCode = input.includes('meet.google.com/')
  ? input.split('meet.google.com/')[1].replace(/^meet\//, '').split(/[/?#]/)[0]
  : input;

console.log(`\nHermes Secretary - joining: ${meetCode}`);
console.log(`Account: ${account || '(default/root profile)'}`);
console.log(`Profile dir: ${resolveSecretDir(account)} (gitignored)`);
console.log('First run for an account: sign into Google in the opened browser window.\n');

const plugin = new SecretaryPlugin();
try {
  await plugin.init({ headless: false, account });
  await plugin.joinMeet(meetCode);
  console.log('Join flow completed. Scraping captions for 60s (Ctrl+C to stop earlier)...');
  const captions = await plugin.scrapeCaptions();
  console.log(`\nCaptured ${captions.length} caption segment(s):`);
  for (const c of captions) console.log('-', c);
} catch (err) {
  console.error('\nJoin/capture failed:', err);
  console.error('Common causes: meeting not active, not invited/admitted, Google sign-in required for this account profile, or Meet UI selectors changed.');
  process.exitCode = 1;
} finally {
  await plugin.close();
}