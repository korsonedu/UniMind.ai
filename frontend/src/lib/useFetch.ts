import { useState, useEffect, useCallback, useRef } from 'react';

type FetchState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
};

/**
 * Generic data-fetching hook with loading/error/data states.
 * Re-fetches when `key` changes; call `refetch()` for manual refresh.
 */
export function useFetch<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  key?: string
): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchId = useRef(0);

  const execute = useCallback(() => {
    const controller = new AbortController();
    const id = ++fetchId.current;
    setLoading(true);
    setError(null);

    fetcher(controller.signal)
      .then((result) => {
        if (id === fetchId.current) {
          setData(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (id === fetchId.current && err?.name !== 'AbortError' && err?.name !== 'CanceledError') {
          setError(err?.message || err?.response?.data?.detail || 'Something went wrong');
        }
      })
      .finally(() => {
        if (id === fetchId.current) setLoading(false);
      });

    return () => controller.abort();
  }, [key]);

  useEffect(() => {
    const cancel = execute();
    return cancel;
  }, [execute]);

  return { data, loading, error, refetch: execute };
}
