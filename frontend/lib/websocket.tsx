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
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const wsUrl = apiUrl.replace(/^http/, "ws") + `/ws/events/?token=${token}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
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
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

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
