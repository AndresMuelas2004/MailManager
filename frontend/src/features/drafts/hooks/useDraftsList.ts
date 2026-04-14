import { useEffect, useState } from "react";

import { listDrafts, syncDrafts } from "../../../api/endpoints/drafts";
import { listAccounts } from "../../../api/endpoints/accounts";
import { toUiError } from "../../../api/client/errors";
import type { DraftOut, AccountOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

type UseDraftsListReturn = {
  drafts: DraftOut[];
  accounts: AccountOut[];
  loading: boolean;
  error: UiError | null;
};

export default function useDraftsList(mailboxId: string): UseDraftsListReturn {
  const [drafts, setDrafts] = useState<DraftOut[]>([]);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UiError | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        // Step 1: GET cached data immediately
        const [cachedDrafts, accountList] = await Promise.all([
          listDrafts(mailboxId),
          listAccounts(mailboxId),
        ]);
        if (cancelled) return;
        setDrafts(cachedDrafts);
        setAccounts(accountList);
        setLoading(false);

        // Step 2: Sync in background, then refresh
        await syncDrafts(mailboxId).catch(() => {});
        if (cancelled) return;

        const freshDrafts = await listDrafts(mailboxId);
        if (!cancelled) setDrafts(freshDrafts);
      } catch (err) {
        if (!cancelled) {
          setError(toUiError(err));
          setLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [mailboxId]);

  return { drafts, accounts, loading, error };
}
