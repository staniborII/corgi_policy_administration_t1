"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getToken } from "@/lib/api";

type Handler = (event: Record<string, unknown>) => void;

interface Subscription {
  prefix: string;
  handler: Handler;
}

interface WebSocketContextValue {
  subscribe: (prefix: string, handler: Handler) => () => void;
  connected: boolean;
}

const WebSocketContext = createContext<WebSocketContextValue>({
  subscribe: () => () => {},
  connected: false,
});

export function useWebSocket() {
  return useContext(WebSocketContext);
}

const RECONNECT_DELAY_MS = 3000;

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const subscriptions = useRef<Set<Subscription>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);

  const cleanup = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const wsUrl = apiUrl.replace(/^http/, "ws") + `/ws/events/?token=${token}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) {
        ws.close();
        return;
      }
      setConnected(true);
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      setConnected(false);
      reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        const eventType: string = data.event || "";
        subscriptions.current.forEach((sub) => {
          if (eventType.startsWith(sub.prefix)) {
            sub.handler(data);
          }
        });
      } catch {
        // ignore malformed messages
      }
    };
  }, []);

  useEffect(() => {
    const timer = setTimeout(connect, 0);
    return () => {
      clearTimeout(timer);
      cleanup();
    };
  }, [connect, cleanup]);

  const subscribe = useCallback((prefix: string, handler: Handler) => {
    const sub: Subscription = { prefix, handler };
    subscriptions.current.add(sub);
    return () => {
      subscriptions.current.delete(sub);
    };
  }, []);

  return (
    <WebSocketContext.Provider value={{ subscribe, connected }}>
      {children}
    </WebSocketContext.Provider>
  );
}
