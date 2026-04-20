import { useCallback, useRef, useState } from 'react';

import { toUiError } from '../../api/client/errors';
import type { UiError } from '../../api/client/errors';

export type UseAsyncReturn<T> = {
  data: T | null;
  loading: boolean;
  error: UiError | null;
  run: (fn: () => Promise<T>) => Promise<T | null>;
  reset: () => void;
  setData: (value: T | null) => void;
  setError: (value: UiError | null) => void;
};

export default function useAsync<T>(): UseAsyncReturn<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UiError | null>(null);
  const activeRef = useRef(0);

  const run = useCallback(async (fn: () => Promise<T>): Promise<T | null> => {
    const token = ++activeRef.current;
    setLoading(true);
    setError(null);
    try {
      const result = await fn();
      if (token === activeRef.current) {
        setData(result);
      }
      return result;
    } catch (err) {
      if (token === activeRef.current) {
        setError(toUiError(err));
      }
      return null;
    } finally {
      if (token === activeRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const reset = useCallback(() => {
    activeRef.current++;
    setData(null);
    setLoading(false);
    setError(null);
  }, []);

  return { data, loading, error, run, reset, setData, setError };
}
