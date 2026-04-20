import { useCallback, useEffect, useState } from 'react';

import { listEmails, syncEmailMetadata } from '../../../api/endpoints/emails';
import { listAccounts } from '../../../api/endpoints/accounts';
import { toUiError } from '../../../api/client/errors';
import type { EmailMetadataOut, AccountOut } from '../../../api/types/dto';
import type { UiError } from '../../../api/client/errors';
import type { EmailBox } from '../../../lib/types';

type UseEmailListReturn = {
  emails: EmailMetadataOut[];
  accounts: AccountOut[];
  loading: boolean;
  syncing: boolean;
  error: UiError | null;
  refresh: () => Promise<void>;
};

export default function useEmailList(
  mailboxId: string,
  box: EmailBox,
  accountId?: string,
): UseEmailListReturn {
  const [emails, setEmails] = useState<EmailMetadataOut[]>([]);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fresh = await listEmails(mailboxId, box, accountId);
      setEmails(fresh);
    } catch (err) {
      setError(toUiError(err));
    }
  }, [mailboxId, box, accountId]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [cachedEmails, accountList] = await Promise.all([
          listEmails(mailboxId, box, accountId),
          listAccounts(mailboxId),
        ]);
        if (cancelled) return;
        setEmails(cachedEmails);
        setAccounts(accountList);
        setLoading(false);

        setSyncing(true);
        await syncEmailMetadata(mailboxId, accountId).catch(() => {});
        if (cancelled) {
          setSyncing(false);
          return;
        }

        const freshEmails = await listEmails(mailboxId, box, accountId);
        if (!cancelled) {
          setEmails(freshEmails);
          setSyncing(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(toUiError(err));
          setLoading(false);
          setSyncing(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [mailboxId, box, accountId]);

  return { emails, accounts, loading, syncing, error, refresh };
}
