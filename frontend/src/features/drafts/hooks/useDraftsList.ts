import { useCallback, useEffect, useState } from "react";

import { listDrafts, syncDrafts } from "../../../api/endpoints/drafts";
import { listAccounts } from "../../../api/endpoints/accounts";
import { toUiError } from "../../../api/client/errors";
import type { DraftOut, AccountOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

type UseDraftsListReturn = {
  drafts: DraftOut[];
  accounts: AccountOut[];
  loading: boolean;
  syncing: boolean;
  error: UiError | null;
  refresh: () => Promise<void>;
  syncAndRefresh: () => Promise<void>;
};

export default function useDraftsList(
  mailboxId: string,
  accountId?: string,
): UseDraftsListReturn {
  const [drafts, setDrafts] = useState<DraftOut[]>([]);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fresh = await listDrafts(mailboxId, accountId);
      setDrafts(fresh);
    } catch (err) {
      setError(toUiError(err));
    }
  }, [mailboxId, accountId]);

  const syncAndRefresh = useCallback(async () => {
    setError(null);
    setSyncing(true);
    try {
      await syncDrafts(mailboxId, accountId);
      const fresh = await listDrafts(mailboxId, accountId);
      setDrafts(fresh);
    } catch (err) {
      setError(toUiError(err));
    } finally {
      setSyncing(false);
    }
  }, [mailboxId, accountId]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [cachedDrafts, accountList] = await Promise.all([
          listDrafts(mailboxId, accountId),
          listAccounts(mailboxId),
        ]);
        if (cancelled) return;
        setDrafts(cachedDrafts);
        setAccounts(accountList);
        setLoading(false);

        await syncDrafts(mailboxId, accountId).catch(() => {});
        if (cancelled) return;

        const freshDrafts = await listDrafts(mailboxId, accountId);
        if (!cancelled) setDrafts(freshDrafts);
      } catch (err) {
        if (!cancelled) {
          setError(toUiError(err));
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [mailboxId, accountId]);

  return { drafts, accounts, loading, syncing, error, refresh, syncAndRefresh };
}
