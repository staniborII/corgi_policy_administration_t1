"use client";

import { useEffect, useRef, useCallback } from "react";
import { useWebSocket } from "@/lib/websocket";

export function useRealtimeRefresh(
  eventPrefix: string | string[],
  onRefresh: () => void,
  debounceMs = 500,
) {
  const { subscribe } = useWebSocket();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  const debouncedRefresh = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onRefreshRef.current();
    }, debounceMs);
  }, [debounceMs]);

  useEffect(() => {
    const prefixes = Array.isArray(eventPrefix) ? eventPrefix : [eventPrefix];
    const unsubs = prefixes.map((p) => subscribe(p, debouncedRefresh));
    return () => {
      unsubs.forEach((u) => u());
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [eventPrefix, subscribe, debouncedRefresh]);
}
