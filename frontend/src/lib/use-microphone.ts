"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Desired chunk size: 100 ms of 16 kHz mono audio.
 *   16 000 samples/s * 0.1 s = 1 600 samples
 *   1 600 samples * 2 bytes (int16) = 3 200 bytes
 */
const SAMPLES_PER_CHUNK = 1600;

/**
 * The ScriptProcessorNode buffer size.  4096 is a safe, widely-supported
 * value.  We accumulate samples internally and flush in 1 600-sample
 * (100 ms) chunks regardless of this size.
 */
const SCRIPT_PROCESSOR_BUFFER = 4096;

/**
 * Convert a Float32Array of audio samples (range -1..+1) to a 16-bit
 * signed PCM ArrayBuffer.
 */
function float32ToInt16(float32: Float32Array): ArrayBuffer {
  const buf = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float32.length; i++) {
    // Clamp to [-1, 1] then scale to int16 range.
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true /* little-endian */);
  }
  return buf;
}

export interface UseMicrophoneReturn {
  /** Request mic permission and begin streaming PCM chunks. */
  start: () => Promise<void>;
  /** Stop recording and release the mic. */
  stop: () => void;
  /** Whether the mic is currently recording. */
  isRecording: boolean;
}

/**
 * React hook for capturing microphone audio as raw 16-bit PCM.
 *
 * Audio is captured at 16 kHz mono and sent as binary frames in 100 ms
 * chunks (1 600 samples = 3 200 bytes) via the provided `sendBinary`
 * callback.
 *
 * Uses a ScriptProcessorNode (deprecated but universally supported and
 * simpler than AudioWorklet for streaming use-cases).
 *
 * @param sendBinary - callback that transmits an ArrayBuffer over WebSocket
 */
export function useMicrophone(
  sendBinary: (data: ArrayBuffer) => void,
): UseMicrophoneReturn {
  const [isRecording, setIsRecording] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  /**
   * Accumulation buffer.  The ScriptProcessorNode fires with whatever
   * buffer size the browser chose; we accumulate here and flush every
   * time we have >= SAMPLES_PER_CHUNK samples.
   */
  const accumulatorRef = useRef<Float32Array>(new Float32Array(0));

  /** Ref to always read the latest sendBinary without re-creating callbacks. */
  const sendBinaryRef = useRef(sendBinary);

  useEffect(() => {
    sendBinaryRef.current = sendBinary;
  }, [sendBinary]);

  const start = useCallback(async () => {
    if (streamRef.current) return; // already recording

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;

      const ctx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;

      // ScriptProcessorNode: 1 input channel, 0 output channels.
      const processor = ctx.createScriptProcessor(SCRIPT_PROCESSOR_BUFFER, 1, 1);
      processorRef.current = processor;

      // Reset accumulator.
      accumulatorRef.current = new Float32Array(0);

      processor.onaudioprocess = (e: AudioProcessingEvent) => {
        const input = e.inputBuffer.getChannelData(0);

        // Append incoming samples to the accumulator.
        const prev = accumulatorRef.current;
        const merged = new Float32Array(prev.length + input.length);
        merged.set(prev);
        merged.set(input, prev.length);
        accumulatorRef.current = merged;

        // Flush as many full 100 ms chunks as we have.
        while (accumulatorRef.current.length >= SAMPLES_PER_CHUNK) {
          const chunk = accumulatorRef.current.slice(0, SAMPLES_PER_CHUNK);
          accumulatorRef.current = accumulatorRef.current.slice(SAMPLES_PER_CHUNK);
          const pcm = float32ToInt16(chunk);
          sendBinaryRef.current(pcm);
        }
      };

      // We must connect through to destination for ScriptProcessorNode to fire.
      source.connect(processor);
      processor.connect(ctx.destination);

      setIsRecording(true);
    } catch (err) {
      console.error("[useMicrophone] Failed to start recording:", err);
    }
  }, []);

  const stop = useCallback(() => {
    // Disconnect audio graph.
    processorRef.current?.disconnect();
    processorRef.current = null;

    sourceRef.current?.disconnect();
    sourceRef.current = null;

    // Close AudioContext.
    audioCtxRef.current?.close();
    audioCtxRef.current = null;

    // Stop all MediaStream tracks (releases mic).
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    // Clear accumulator.
    accumulatorRef.current = new Float32Array(0);

    setIsRecording(false);
  }, []);

  return { start, stop, isRecording };
}
