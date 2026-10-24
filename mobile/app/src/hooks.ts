import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  /** true once a request has been running for > 5 s (likely a cold-starting Hugging Face Space) */
  slow: boolean;
  run: (fn: () => Promise<T>) => Promise<T | null>;
  reset: () => void;
  setData: (d: T | null) => void;
}

export function useAsync<T>(): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const seq = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(timer.current), []);

  const run = useCallback(async (fn: () => Promise<T>) => {
    const id = ++seq.current;
    setLoading(true); setError(null); setSlow(false);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => id === seq.current && setSlow(true), 5000);
    try {
      const d = await fn();
      if (id === seq.current) setData(d);
      return d;
    } catch (e) {
      if (id === seq.current) setError(e instanceof Error ? e : new Error(String(e)));
      return null;
    } finally {
      if (id === seq.current) { setLoading(false); setSlow(false); clearTimeout(timer.current); }
    }
  }, []);
  const reset = useCallback(() => { seq.current++; setData(null); setError(null); setLoading(false); setSlow(false); }, []);
  return { data, error, loading, slow, run, reset, setData };
}

/** Load once on mount (and whenever `deps` change). */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const s = useAsync<T>();
  const reload = useCallback(() => s.run(fn), deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload]);
  return { ...s, reload };
}
