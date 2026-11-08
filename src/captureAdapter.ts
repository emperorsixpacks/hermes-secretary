/**
 * Capture Adapter Interface
 *
 * Defines the contract for different caption/audio capture sources.
 * Phase 1: Google Meet caption scraping (free, works today)
 * Phase 2: Whisper-based audio transcription (stretch goal)
 * Phase 3: Real-time audio tap (future)
 */

import { SecretaryPlugin } from './index.js';

export type CaptionSource = 'google_meet' | 'whisper_local' | 'upload' | 'manual';

export interface CaptionSegment {
  speaker: string | null;
  text: string;
  startTime: number; // in seconds
  endTime: number; // in seconds
  source: CaptionSource;
}

export interface CaptureAdapter {
  /**
   * Initialize the adapter (launch browser, load profile, etc.)
   */
  init(): Promise<void>;

  /**
   * Start capturing captions from the selected source.
   * Returns an async iterator of CaptionSegment.
   */
  startCapturing(): AsyncGenerator<CaptionSegment>;

  /**
   * Stop capturing and clean up resources.
   */
  stop(): Promise<void>;

  /**
   * Get the current source being used.
   */
  getSource(): CaptionSource;
}

/**
 * Google Meet Caption Adapter - Phase 1 implementation
 * Scrapes live captions from Google Meet using Playwright.
 */
export class GoogleMeetCaptionAdapter implements CaptureAdapter {
  private plugin: SecretaryPlugin;
  private source: CaptionSource = 'google_meet';
  private running: boolean = false;

  constructor() {
    this.plugin = new SecretaryPlugin();
  }

  async init(): Promise<void> {
    await this.plugin.init();
  }

  async startCapturing(): Promise<AsyncGenerator<CaptionSegment>> {
    if (this.running) {
      throw new Error('Capture already running');
    }
    this.running = true;

    // Return an async generator that scrapes captions
    return this.scrapeLoop();
  }

  private async* scrapeLoop(): AsyncGenerator<CaptionSegment> {
    // Initial delay to let the meeting settle
    await new Promise(resolve => setTimeout(resolve, 3000));

    while (this.running) {
      const captions = await this.plugin.scrapeCaptions();

      for (const text of captions) {
        if (!this.running) break;

        yield {
          speaker: null, // Best effort - will be improved later
          text,
          startTime: Date.now() / 1000 - 3,
          endTime: Date.now() / 1000,
          source: 'google_meet',
        };
      }

      // Wait before next scrape cycle
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }

  async stop(): Promise<void> {
    this.running = false;
    await this.plugin.close();
  }

  getSource(): CaptionSource {
    return this.source;
  }
}

/**
 * Whisper Local Adapter - Phase 2 implementation
 * Transcribes audio using local Whisper models.
 * Currently a stub - full implementation requires:
 * - Audio capture from browser/incoming tracks
 * - faster-whisper pipeline
 * - Voice-activity detection for segmenting
 */
export class WhisperLocalAdapter implements CaptureAdapter {
  private source: CaptionSource = 'whisper_local';
  private running: boolean = false;
  private plugin: SecretaryPlugin;

  constructor() {
    this.plugin = new SecretaryPlugin();
    // Whisper model would be loaded here
  }

  async init(): Promise<void> {
    // Load Whisper model (e.g., tiny, base, small)
    // Model choice: smaller keeps up with live speech, larger is more accurate
    console.log('Loading Whisper model...');
    this.running = true;
  }

  async startCapturing(): Promise<AsyncGenerator<CaptionSegment>> {
    if (this.running) {
      throw new Error('Capture already running');
    }
    this.running = true;
    return this.transcribeLoop();
  }

  private async* transcribeLoop(): AsyncGenerator<CaptionSegment> {
    // Phase 2: Would capture audio stream and transcribe
    // For now, yield placeholder
    while (this.running) {
      yield {
        speaker: null,
        text: '[Whisper transcription - Phase 2]',
        startTime: Date.now() / 1000,
        endTime: Date.now() / 1000 + 5,
        source: 'whisper_local',
      };
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
  }

  async stop(): Promise<void> {
    this.running = false;
  }

  getSource(): CaptionSource {
    return this.source;
  }
}

/**
 * Unified Factory - creates the appropriate adapter based on config
 */
export function createAdapter(
  config: { source: CaptionSource; meetCode?: string }
): CaptureAdapter {
  switch (config.source) {
    case 'google_meet':
      const meetAdapter = new GoogleMeetCaptionAdapter();
      // Could configure meetCode if needed
      return meetAdapter;
    case 'whisper_local':
      return new WhisperLocalAdapter();
    case 'upload':
      // Would handle audio file upload
      return new WhisperLocalAdapter(); // Stub
    case 'manual':
      // Would handle manual text input
      return new WhisperLocalAdapter(); // Stub
    default:
      return new GoogleMeetCaptionAdapter();
  }
}