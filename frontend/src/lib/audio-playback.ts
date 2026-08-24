/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * AudioPlayer -- utility class for playing raw PCM audio received from the
 * server (Gemini voice output).
 *
 * PCM format from the server:
 *   - 16-bit signed integer
 *   - 24 kHz sample rate
 *   - Mono (single channel)
 *
 * Chunks are scheduled back-to-back on the Web Audio timeline so that
 * playback is seamless even when chunks arrive with jitter.
 *
 * This is a plain class (no React dependency) so it can be instantiated
 * once and shared across renders via a useRef.
 */
export class AudioPlayer {
  private ctx: AudioContext | null = null;
  private nextTime: number = 0;

  // ── public API ───────────────────────────────────────────────────

  /**
   * Schedule a PCM chunk for playback.
   *
   * @param pcmData - ArrayBuffer of 16-bit signed, 24 kHz, mono PCM
   */
  play(pcmData: ArrayBuffer): void {
    const ctx = this.getContext();

    // Convert Int16 PCM to Float32 for the Web Audio API.
    const int16 = new Int16Array(pcmData);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    // Create an AudioBuffer and fill it.
    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);

    // Create a one-shot source node.
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // Schedule seamlessly after the previous chunk.
    const now = ctx.currentTime;
    const startAt = Math.max(now, this.nextTime);
    source.start(startAt);
    this.nextTime = startAt + buffer.duration;
  }

  /**
   * Stop all scheduled playback and release the AudioContext.
   * After calling stop() a new context will be created lazily on the next
   * call to play().
   */
  stop(): void {
    if (this.ctx) {
      this.ctx.close().catch(() => {
        // best-effort -- close can reject if already closed
      });
      this.ctx = null;
    }
    this.nextTime = 0;
  }

  // ── internals ────────────────────────────────────────────────────

  /**
   * Lazily create (or resume) an AudioContext at the playback sample rate.
   */
  private getContext(): AudioContext {
    if (!this.ctx || this.ctx.state === "closed") {
      this.ctx = new AudioContext({ sampleRate: 24000 });
      this.nextTime = 0;
    }

    // Safari and some mobile browsers require a resume after user gesture.
    if (this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {
        // best-effort
      });
    }

    return this.ctx;
  }
}
