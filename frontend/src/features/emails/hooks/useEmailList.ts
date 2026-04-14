import { useEffect, useState } from "react";

import { listEmails, syncEmailMetadata } from "../../../api/endpoints/emails";
import { listAccounts } from "../../../api/endpoints/accounts";
import { toUiError } from "../../../api/client/errors";
import type { EmailMetadataOut, AccountOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";
import type { EmailBox } from "../../../lib/types";

type UseEmailListReturn = {
  emails: EmailMetadataOut[];
  accounts: AccountOut[];
  loading: boolean;
  error: UiError | null;
};

export default function useEmailList(
  mailboxId: string,
  box: EmailBox,
): UseEmailListReturn {
  const [emails, setEmails] = useState<EmailMetadataOut[]>([]);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UiError | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        // Step 1: GET cached data immediately
        const [cachedEmails, accountList] = await Promise.all([
          listEmails(mailboxId, box),
          listAccounts(mailboxId),
        ]);
        if (cancelled) return;
        setEmails(cachedEmails);
        setAccounts(accountList);
        setLoading(false);

        // Step 2: Sync in background, then refresh
        await syncEmailMetadata(mailboxId).catch(() => {});
        if (cancelled) return;

        const freshEmails = await listEmails(mailboxId, box);
        if (!cancelled) setEmails(freshEmails);
      } catch (err) {
        if (!cancelled) {
          setError(toUiError(err));
          setLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [mailboxId, box]);

  return { emails, accounts, loading, error };
}
