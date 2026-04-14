import { useCallback, useEffect, useState } from "react";

import { toUiError } from "../../api/client/errors";
import type { UiError } from "../../api/client/errors";

export type UseCacheThenSyncOpts<T> = {
  fetchData: () => Promise<T>;
  sync: () => Promise<unknown>;
  deps: ReadonlyArray<unknown>;
};

export type UseCacheThenSyncReturn<T> = {
  data: T | null;
  loading: boolean;
  syncing: boolean;
  error: UiError | null;
  refresh: () => Promise<void>;
  syncAndRefresh: () => Promise<void>;
};

/**
 * Shows cached data immediately, then triggers a background sync and refetches.
 * Used by list hooks that hit a local cache first and reconcile with the provider.
 */
export default function useCacheThenSync<T>(
  opts: UseCacheThenSyncOpts<T>,
): UseCacheThenSyncReturn<T> {
  const { fetchData, sync, deps } = opts;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fresh = await fetchData();
      setData(fresh);
    } catch (err) {
      setError(toUiError(err));
    }
    // fetchData identity is caller-controlled via deps; safe to omit here
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const syncAndRefresh = useCallback(async () => {
    setError(null);
    setSyncing(true);
    try {
      await sync();
      const fresh = await fetchData();
      setData(fresh);
    } catch (err) {
      setError(toUiError(err));
    } finally {
      setSyncing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const cached = await fetchData();
        if (cancelled) return;
        setData(cached);
        setLoading(false);

        await sync().catch(() => {});
        if (cancelled) return;

        const fresh = await fetchData();
        if (!cancelled) setData(fresh);
      } catch (err) {
        if (!cancelled) {
          setError(toUiError(err));
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, syncing, error, refresh, syncAndRefresh };
}
