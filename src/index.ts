/**
 * Hermes Secretary Plugin
 * Scrapes Google Meet live captions and provides transcription via Whisper.
 *
 * Phase 1: Caption scraping from Google Meet (free, no Whisper needed initially)
 * Phase 2: Audio tap with Whisper transcription (stretch goal)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, BrowserContext, Page } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// Secret/profile root kept relative to the plugin root (hermes-secretary).
// Each account gets its own subdirectory: ./secret/<account>/
const SECRET_ROOT = path.resolve(__dirname, '..', 'secret');

interface MeetingConfig {
  url: string;
  meetingCode: string;
  attendeeEmails: string[];
  account?: string;
}

function sanitizeAccountName(name: string): string {
  const cleaned = name.trim().replace(/[^a-zA-Z0-9._@-]+/g, '-').replace(/^-+|-+$/g, '');
  if (!cleaned) throw new Error('Invalid account name');
  return cleaned;
}

export function resolveSecretDir(account?: string): string {
  if (!account) return SECRET_ROOT;
  return path.join(SECRET_ROOT, sanitizeAccountName(account));
}

export class SecretaryPlugin {
  private context: BrowserContext | null = null;
  private page: Page | null = null;
  private secretDir: string = SECRET_ROOT;

  /**
   * Launch browser with a signed-in profile for Google Meet.
   * Uses a persistent context stored in ./secret/<account> (relative to plugin root)
   * so you can sign in once per account and reuse sessions.
   */
  async init(options?: { headless?: boolean; account?: string }): Promise<void> {
    const headless = options?.headless ?? false;
    this.secretDir = resolveSecretDir(options?.account);
    fs.mkdirSync(this.secretDir, { recursive: true });
    this.context = await chromium.launchPersistentContext(this.secretDir, {
      headless,
      viewport: { width: 1280, height: 720 },
      args: headless ? ['--no-sandbox', '--disable-setuid-sandbox'] : [],
    });
    this.page = this.context.pages()[0] ?? (await this.context.newPage());
  }

  getSecretDir(): string {
    return this.secretDir;
  }

  /**
   * Join a Google Meet using the meeting code or full URL.
   * Handles the join screen, "Ask to join" prompts, and mutes mic/camera.
   */
  async joinMeet(meetingCodeOrUrl: string): Promise<void> {
    if (!this.page) throw new Error('Browser not initialized. Call init() first.');

    const code = this.normalizeMeetCode(meetingCodeOrUrl);
    const url = `https://meet.google.com/${code}`;
    await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await this.page.waitForTimeout(4000);

    // Wait for and handle the join lobby/button
    await this.handleJoinScreen();

    // Mute mic and camera
    await this.muteAudioVideo();
  }

  private normalizeMeetCode(value: string): string {
    let v = (value || '').trim();
    if (v.includes('meet.google.com/')) v = v.split('meet.google.com/')[1];
    v = v.replace(/^meet\//, '').split(/[?#]/)[0].replace(/\/+$/g, '');
    return v;
  }

  private async handleJoinScreen(): Promise<void> {
    if (!this.page) return;
    // Google Meet's join screen changes often; try several selectors/labels.
    const candidates = [
      'button:has-text("Join now")',
      'button:has-text("Ask to join")',
      'button:has-text("Ask to be let in")',
      '[aria-label*="Join now"]',
      '[aria-label*="Ask to join"]',
      'text=Join now',
      'text=Ask to join',
    ];

    for (let attempt = 0; attempt < 3; attempt++) {
      for (const sel of candidates) {
        try {
          const loc = this.page.locator(sel).first();
          if (await loc.isVisible({ timeout: 1500 }).catch(() => false)) {
            await loc.click({ timeout: 3000 }).catch(() => {});
            await this.page.waitForTimeout(2000);
            return;
          }
        } catch {
          // selector may not exist in this UI variant
        }
      }
      await this.page.waitForTimeout(1500);
    }
  }

  private async muteAudioVideo(): Promise<void> {
    if (!this.page) return;
    for (const sel of [
      '[aria-label*="Turn off microphone" i]',
      'button[aria-label*="microphone" i]',
      '[aria-label*="Turn off camera" i]',
      'button[aria-label*="camera" i]',
    ]) {
      try {
        const loc = this.page.locator(sel).first();
        if (await loc.isVisible({ timeout: 1000 }).catch(() => false)) {
          const aria = ((await loc.getAttribute('aria-label')) || '').toLowerCase();
          if (aria.includes('turn off') || aria.includes('mute')) {
            await loc.click({ timeout: 1500 }).catch(() => {});
          }
        }
      } catch {
        // ignore
      }
    }
  }

  /**
   * Scrape live captions from Google Meet.
   * Returns caption text as it appears.
   */
  async scrapeCaptions(): Promise<string[]> {
    if (!this.page) throw new Error('Browser not initialized.');

    // Google Meet captions appear in a specific DOM area
    // This selector may need updating as Meet changes its UI
    const captionContainer = this.page.locator('.lNImpb, [data-test-id="captions"]');

    const captions: string[] = [];
    const timeout = 60000; // Listen for 60 seconds
    const start = Date.now();

    while (Date.now() - start < timeout) {
      const containerHandle = await captionContainer.elementHandle();
      if (containerHandle) {
        const text = await containerHandle.evaluate((el: HTMLElement) => el.innerText.trim());
        if (text && !captions.includes(text)) {
          captions.push(text);
        }
      }
      await this.page.waitForTimeout(1000);
    }

    return captions;
  }

  /**
   * Capture incoming audio stream and send to Whisper for transcription.
   * Phase 2: Whisper integration.
   */
  async captureAudioWithWhisper(): Promise<string[]> {
    // Phase 2: Inject script to grab audio tracks and send to Python/Whisper
    // This is the "audio tap" approach - captures raw audio instead of relying on Meet captions
    return [];
  }

  async close(): Promise<void> {
    if (this.context) {
      await this.context.close();
      this.context = null;
      this.page = null;
    }
  }
}

// Example usage
(async () => {
  const plugin = new SecretaryPlugin();
  try {
    await plugin.init();
    await plugin.joinMeet('your-meeting-code');
    const captions = await plugin.scrapeCaptions();
    console.log('Captions:', captions);
  } finally {
    await plugin.close();
  }
})();