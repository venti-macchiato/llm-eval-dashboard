import { useCallback, useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Minimal fetch-on-mount hook with a manual reload trigger. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((value) => {
        if (!alive) return;
        setData(value);
        setError(null);
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}

/** Call `fn` every `ms` while `active`, invoking `onData` with each result. */
export function usePolling<T>(
  fn: () => Promise<T>,
  active: boolean,
  ms: number,
  onData: (value: T) => void,
) {
  useEffect(() => {
    if (!active) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const value = await fn();
        if (alive) onData(value);
      } catch {
        /* keep polling through transient errors */
      }
      if (alive) timer = window.setTimeout(tick, ms);
    };
    tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ms, fn]);
}
