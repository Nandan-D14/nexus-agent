/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { authenticatedFetch } from "./api-client";
import type { WsMessage, WsCommand } from "./message-types";

/** Ready-state constants mirroring the WebSocket API. */
export const ReadyState = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
} as const;

export type ReadyStateValue = (typeof ReadyState)[keyof typeof ReadyState];

export interface UseWebSocketReturn {
  /** Send a raw string frame. */
  send: (data: string) => void;
  /** Send a binary (ArrayBuffer) frame -- used for audio. */
  sendBinary: (data: ArrayBuffer) => void;
  /** Send a typed JSON command (serialised automatically). */
  sendJson: (cmd: WsCommand) => void;
  /** The most recent parsed server message (text frame). */
  lastMessage: WsMessage | null;
  /** Whether the socket is currently in the OPEN state. */
  isConnected: boolean;
  /** Raw WebSocket readyState value. */
  readyState: ReadyStateValue;
  /** Assign a callback to receive binary (audio) frames. */
  onBinaryMessageRef: React.MutableRefObject<
    ((data: ArrayBuffer) => void) | null
  >;
  /** Assign a callback to receive every JSON message (no batching loss). */
  onJsonMessageRef: React.MutableRefObject<
    ((msg: WsMessage) => void) | null
  >;
}

const MAX_RECONNECT_ATTEMPTS = 3;
const BASE_DELAY_MS = 1000;
const NON_RETRYABLE_CLOSE_CODES = new Set([4001, 4004, 4403, 4429]);

type DurableReplayEvent = {
  event_id?: string;
  task_id?: string;
  run_id?: string | null;
  type?: string;
  payload?: Record<string, unknown>;
  seq?: number;
};

type DurableReplayResponse = {
  events?: DurableReplayEvent[];
  last_seq?: number;
};

function resolveWebSocketTarget(target: string): { url: string; protocols?: string[] } {
  try {
    const parsed = new URL(target);
    const ticket = parsed.searchParams.get("ticket");
    if (!ticket) {
      return { url: target };
    }
    parsed.searchParams.delete("ticket");
    const cleanUrl = parsed.toString();
    return { url: cleanUrl, protocols: [ticket] };
  } catch {
    return { url: target };
  }
}

function isDurableTaskId(value: string | null | undefined): value is string {
  return typeof value === "string" && value.startsWith("task_");
}

function eventKey(message: WsMessage): string | null {
  if (message.event_id) {
    return `event:${message.event_id}`;
  }
  if (message.task_id && typeof message.seq === "number" && message.seq > 0) {
    return `seq:${message.task_id}:${message.seq}`;
  }
  return null;
}

function replayEventToMessage(event: DurableReplayEvent): WsMessage | null {
  if (!event.type) {
    return null;
  }
  const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
  return {
    ...payload,
    type: event.type,
    event_id: event.event_id,
    task_id: event.task_id,
    run_id: event.run_id ?? undefined,
    seq: event.seq,
  } as WsMessage;
}

export interface UseWebSocketOptions {
  /** WS auth ticket. Consumed only at (re)connect time; rotating it does NOT
   * tear down a healthy socket. */
  ticket?: string | null;
  /** Durable task id for event replay/dedupe after reconnect. */
  durableTaskId?: string | null;
}

/** Max outbound frames buffered while the socket is not OPEN. */
const MAX_OUTBOUND_BUFFER = 50;

/**
 * React hook for WebSocket connection management.
 */
export function useWebSocket(
  url: string | null,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const { ticket = null, durableTaskId = null } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const [readyState, setReadyState] = useState<ReadyStateValue>(ReadyState.CLOSED);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);

  /** Mutable ref so consumers can swap the binary handler without re-renders. */
  const onBinaryMessageRef = useRef<((data: ArrayBuffer) => void) | null>(null);
  /** Mutable ref so consumers can handle every JSON message without React batching loss. */
  const onJsonMessageRef = useRef<((msg: WsMessage) => void) | null>(null);

  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<(target: string) => void>(() => {});
  /** Keeps the latest url so the reconnect closure always sees it. */
  const urlRef = useRef(url);
  /** Latest ticket, read at connect time. Updated without reconnecting. */
  const ticketRef = useRef<string | null>(ticket);
  /** Outbound frames buffered while the socket is not OPEN; flushed on open. */
  const pendingOutboundRef = useRef<Array<string | ArrayBuffer>>([]);
  const durableTaskIdRef = useRef<string | null>(
    isDurableTaskId(durableTaskId) ? durableTaskId : null,
  );
  const lastSeqRef = useRef(0);
  const seenEventKeysRef = useRef<Set<string>>(new Set());
  const replayInFlightRef = useRef(false);
  const replayBufferRef = useRef<WsMessage[]>([]);
  const hasOpenedRef = useRef(false);

  useEffect(() => {
    urlRef.current = url;
  }, [url]);

  useEffect(() => {
    // Rotating the ticket must NOT trigger a reconnect: store it in a ref so the
    // next (re)connect picks up the fresh value, but the current socket stays up.
    ticketRef.current = ticket;
  }, [ticket]);

  useEffect(() => {
    const nextTaskId = isDurableTaskId(durableTaskId) ? durableTaskId : null;
    if (durableTaskIdRef.current !== nextTaskId) {
      lastSeqRef.current = 0;
      seenEventKeysRef.current.clear();
      replayBufferRef.current = [];
    }
    durableTaskIdRef.current = nextTaskId;
  }, [durableTaskId]);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimer.current !== null) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
  }, []);

  const dispatchJsonMessage = useCallback((message: WsMessage) => {
    if (isDurableTaskId(message.task_id)) {
      durableTaskIdRef.current = message.task_id;
    }

    const key = eventKey(message);
    if (key) {
      if (seenEventKeysRef.current.has(key)) {
        return;
      }
      seenEventKeysRef.current.add(key);
    }

    if (typeof message.seq === "number" && Number.isFinite(message.seq)) {
      lastSeqRef.current = Math.max(lastSeqRef.current, message.seq);
    }

    onJsonMessageRef.current?.(message);
    setLastMessage(message);
  }, []);

  const flushReplayBuffer = useCallback(() => {
    const buffered = replayBufferRef.current;
    replayBufferRef.current = [];
    buffered.forEach(dispatchJsonMessage);
  }, [dispatchJsonMessage]);

  const replayMissedEvents = useCallback(
    async (taskId: string, afterSeq: number) => {
      const response = await authenticatedFetch(
        `/api/v1/tasks/${encodeURIComponent(taskId)}/events?after_seq=${afterSeq}`,
      );
      if (!response.ok) {
        return;
      }
      const body = (await response.json().catch(() => null)) as DurableReplayResponse | null;
      const replayed = Array.isArray(body?.events) ? body.events : [];
      replayed
        .map(replayEventToMessage)
        .filter((message): message is WsMessage => message !== null)
        .forEach(dispatchJsonMessage);
      if (typeof body?.last_seq === "number" && Number.isFinite(body.last_seq)) {
        lastSeqRef.current = Math.max(lastSeqRef.current, body.last_seq);
      }
    },
    [dispatchJsonMessage],
  );

  /** Surface a synthetic error to consumers via the same path as server
   * messages (onJsonMessageRef) so the page's `case "error"` handler runs and
   * the UI recovers instead of hanging on a "thinking" state. */
  const surfaceError = useCallback((code: string, message: string) => {
    const errorMsg = { type: "error", code, message } as WsMessage;
    onJsonMessageRef.current?.(errorMsg);
    setLastMessage(errorMsg);
  }, []);

  const connect = useCallback((target: string) => {
    // Tear down any existing socket first.
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    // Read the latest ticket at connect time (subprotocol handshake). Strip any
    // stale ?ticket= from the url so a rotated ticket can never be sent stale.
    const { url: cleanUrl } = resolveWebSocketTarget(target);
    const currentTicket = ticketRef.current;
    const ws = currentTicket
      ? new WebSocket(cleanUrl, [currentTicket])
      : new WebSocket(cleanUrl);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    setReadyState(ReadyState.CONNECTING);

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      setReadyState(ReadyState.OPEN);

      // Flush any frames queued while the socket was down (in order).
      if (pendingOutboundRef.current.length > 0) {
        const buffered = pendingOutboundRef.current;
        pendingOutboundRef.current = [];
        for (const frame of buffered) {
          try {
            ws.send(frame);
          } catch (error) {
            console.warn("[useWebSocket] Failed to flush buffered frame:", error);
          }
        }
      }

      const shouldReplay = hasOpenedRef.current && durableTaskIdRef.current !== null;
      const replayTaskId = durableTaskIdRef.current;
      const replayAfterSeq = lastSeqRef.current;
      hasOpenedRef.current = true;

      if (shouldReplay && replayTaskId) {
        replayInFlightRef.current = true;
        void replayMissedEvents(replayTaskId, replayAfterSeq)
          .catch((error) => {
            console.warn("[useWebSocket] Durable event replay failed:", error);
          })
          .finally(() => {
            replayInFlightRef.current = false;
            flushReplayBuffer();
          });
      }

      // Send a ping every 30 s to keep Cloud Run alive and the WS from timing out
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        } else {
          clearInterval(pingInterval);
        }
      }, 30_000);

      ws.addEventListener("close", () => clearInterval(pingInterval), { once: true });
    };

    ws.onclose = (event) => {
      setReadyState(ReadyState.CLOSED);

      const failBufferedSends = () => {
        if (pendingOutboundRef.current.length > 0) {
          pendingOutboundRef.current = [];
          surfaceError(
            "WS_SEND_FAILED",
            "Your message could not be delivered. Please resend.",
          );
        }
      };

      if (NON_RETRYABLE_CLOSE_CODES.has(event.code)) {
        setLastMessage({
          type: "error",
          code: `WS_CLOSED_${event.code}`,
          message: event.reason || "WebSocket connection was closed.",
        });
        reconnectAttempts.current = MAX_RECONNECT_ATTEMPTS;
        failBufferedSends();
        return;
      }

      if (
        reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS &&
        urlRef.current !== null
      ) {
        const delay = BASE_DELAY_MS * Math.pow(2, reconnectAttempts.current);
        reconnectAttempts.current += 1;
        reconnectTimer.current = setTimeout(() => {
          if (urlRef.current) {
            connectRef.current(urlRef.current);
          }
        }, delay);
      } else {
        // Reconnect budget exhausted (or intentionally disconnected): stop
        // holding queued frames hostage so the UI can surface a retry.
        failBufferedSends();
      }
    };

    ws.onerror = () => {
      // The browser fires onclose after onerror, so we handle reconnection there.
    };

    ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        onBinaryMessageRef.current?.(event.data);
      } else if (typeof event.data === "string") {
        try {
          const parsed = JSON.parse(event.data) as WsMessage;
          if (replayInFlightRef.current) {
            replayBufferRef.current.push(parsed);
          } else {
            dispatchJsonMessage(parsed);
          }
        } catch {
          console.warn("[useWebSocket] Failed to parse text frame:", event.data);
        }
      }
    };
  }, [dispatchJsonMessage, flushReplayBuffer, replayMissedEvents, surfaceError]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    clearReconnectTimer();
    reconnectAttempts.current = 0;
    hasOpenedRef.current = false;
    replayInFlightRef.current = false;
    replayBufferRef.current = [];

    if (url) {
      queueMicrotask(() => connect(url));
    } else {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
        queueMicrotask(() => setReadyState(ReadyState.CLOSED));
      }
    }

    return () => {
      clearReconnectTimer();
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [clearReconnectTimer, connect, url]);

  const send = useCallback((data: string) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(data);
      return;
    }
    // Socket not OPEN (connecting / mid-reconnect). Buffer control/text frames
    // and flush them on reconnect so a prompt sent during a ticket-rotation
    // reconnect is not silently lost. Drop-oldest past the cap.
    if (urlRef.current !== null) {
      const buffer = pendingOutboundRef.current;
      if (buffer.length >= MAX_OUTBOUND_BUFFER) {
        buffer.shift();
      }
      buffer.push(data);
    } else {
      surfaceError(
        "WS_SEND_FAILED",
        "Not connected. Your message could not be delivered.",
      );
    }
  }, [surfaceError]);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    // Audio is real-time and ephemeral -- never buffer stale PCM; just drop it
    // when the socket is not OPEN. The mic stream resumes on reconnect.
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const sendJson = useCallback(
    (cmd: WsCommand) => {
      send(JSON.stringify(cmd));
    },
    [send],
  );

  const isConnected = readyState === ReadyState.OPEN;

  return {
    send,
    sendBinary,
    sendJson,
    lastMessage,
    isConnected,
    readyState,
    onBinaryMessageRef,
    onJsonMessageRef,
  };
}
