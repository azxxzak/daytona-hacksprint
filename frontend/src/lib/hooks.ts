"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import type { Test, TestSummary } from "./types";

export type Loadable<T> = { data: T | null; error: ApiError | null; loading: boolean; reload: () => void };

export function useApi<T>(path: string | null): Loadable<T> {
  const [tick, setTick] = useState(0);
  const key = `${path}#${tick}`;
  const [res, setRes] = useState<{ key: string; data: T | null; error: ApiError | null } | null>(null);

  useEffect(() => {
    if (!path) return;
    const ac = new AbortController();
    api<T>(path, { signal: ac.signal })
      .then((d) => setRes({ key, data: d, error: null }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setRes({ key, data: null, error: e instanceof ApiError ? e : new ApiError(0, "network") });
      });
    return () => ac.abort();
  }, [path, key]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data: res?.data ?? null, error: res?.error ?? null, loading: !!path && res?.key !== key, reload };
}

/** Poll a path every `ms` while `shouldPoll(data)` holds. */
export function usePolled<T>(path: string, shouldPoll: (d: T) => boolean, ms: number): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const pollRef = useRef(shouldPoll);
  useEffect(() => {
    pollRef.current = shouldPoll;
  });

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const ac = new AbortController();
    const run = async () => {
      try {
        const d = await api<T>(path, { signal: ac.signal });
        if (stop) return;
        setData(d);
        setError(null);
        setLoading(false);
        if (pollRef.current(d)) timer = setTimeout(run, ms);
      } catch (e) {
        if (stop || (e instanceof DOMException && e.name === "AbortError")) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "network"));
        setLoading(false);
        // transient network trouble: keep trying; hard errors (4xx) stop
        if (!(e instanceof ApiError) || e.status === 0 || e.status >= 500) timer = setTimeout(run, ms * 2);
      }
    };
    run();
    return () => {
      stop = true;
      ac.abort();
      clearTimeout(timer);
    };
  }, [path, ms, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}

export const isActive = (s: { status: TestSummary["status"] }) => s.status === "queued" || s.status === "running";
export type { Test, TestSummary };
