import { formatApiErrorToast } from '@/lib/apiError';
import { useState, useEffect, useCallback, useRef } from 'react';

type FetchState<T> = { data: T | null; loading: boolean; error: string | null; refetch: () => void };

export function useFetch<T>(fetcher: (signal: AbortSignal) => Promise<T>, key?: string): FetchState<T> {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{ key?: string; version: number; data: T | null; error: string | null } | null>(null);
  const fetchId = useRef(0);
  const fetcherRef = useRef(fetcher);
  useEffect(() => { fetcherRef.current = fetcher; }, [fetcher]);
  useEffect(() => {
    const controller = new AbortController();
    const id = ++fetchId.current;
    fetcherRef.current(controller.signal)
      .then(data => { if (id === fetchId.current) setResult({ key, version, data, error: null }); })
      .catch((error: unknown) => {
        const name = error instanceof Error ? error.name : '';
        if (id === fetchId.current && name !== 'AbortError' && name !== 'CanceledError') {
          setResult(previous => ({ key, version, data: previous?.data ?? null, error: formatApiErrorToast(error, 'Something went wrong') }));
        }
      });
    return () => controller.abort();
  }, [key, version]);
  const refetch = useCallback(() => setVersion(previous => previous + 1), []);
  const loading = !result || result.key !== key || result.version !== version;
  return { data: result?.data ?? null, loading, error: loading ? null : result.error, refetch };
}
