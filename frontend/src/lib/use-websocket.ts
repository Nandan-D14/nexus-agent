"use client";

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";
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
}

const MAX_RECONNECT_ATTEMPTS = 3;
const BASE_DELAY_MS = 1000;

/**
 * React hook for WebSocket connection management.
 *
 * Pass `null` as the url to keep the socket disconnected (useful when the
 * session has not been created yet). Once a non-null url is provided the
 * hook connects automatically.
 *
 * Auto-reconnects with exponential back-off (1 s, 2 s, 4 s, max 3 attempts).
 */
export function useWebSocket(url: string | null): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const [readyState, setReadyState] = useState<ReadyStateValue>(ReadyState.CLOSED);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);

  /** Mutable ref so consumers can swap the binary handler without re-renders. */
  const onBinaryMessageRef = useRef<((data: ArrayBuffer) => void) | null>(null);

  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<(target: string) => void>(() => {});
  /** Keeps the latest url so the reconnect closure always sees it. */
  const urlRef = useRef(url);

  // ── helpers ──────────────────────────────────────────────────────

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimer.current !== null) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
  }, []);

  const connect = useEffectEvent((target: string) => {
    // Tear down any existing socket first.
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const ws = new WebSocket(target);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    setReadyState(ReadyState.CONNECTING);

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      setReadyState(ReadyState.OPEN);
    };

    ws.onclose = () => {
      setReadyState(ReadyState.CLOSED);

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
          setLastMessage(parsed);
        } catch {
          console.warn("[useWebSocket] Failed to parse text frame:", event.data);
        }
      }
    };
  });

  useEffect(() => {
    urlRef.current = url;
  }, [url]);

  useEffect(() => {
    connectRef.current = connect;
  });

  // ── open / close when url changes ────────────────────────────────

  useEffect(() => {
    clearReconnectTimer();
    reconnectAttempts.current = 0;

    if (url) {
      connect(url);
    } else {
      // url became null -- disconnect.
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
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
  }, [url, clearReconnectTimer]);

  // ── send helpers ─────────────────────────────────────────────────

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
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

  // ── derived ──────────────────────────────────────────────────────

  const isConnected = readyState === ReadyState.OPEN;

  return {
    send,
    sendBinary,
    sendJson,
    lastMessage,
    isConnected,
    readyState,
    onBinaryMessageRef,
  };
}
