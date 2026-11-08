/**
 * Run locally to join a Google Meet with a persistent signed-in profile.
 *
 * Usage:
 *   node join-meet.mjs hfz-wssx-rpa
 *   node join-meet.mjs https://meet.google.com/hfz-wssx-rpa
 *
 * First run: a browser window opens; sign into Google. The session is saved in
 * ./secret (relative to the hermes-secretary plugin root) and gitignored.
 *
 * Note: Node 24 can strip simple TS types, but this project uses interfaces.
 * For local runs, use tsx (recommended): npx tsx join-meet.ts
 * A tsx-based runner is provided as join-meet.ts below.
 */
console.log('This .mjs wrapper is informational. Use: npx tsx join-meet.ts <meet-code-or-url>');