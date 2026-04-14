import { useEffect, useState } from "react";

import { listAccounts } from "../../../api/endpoints/accounts";
import { syncEmailMetadata, listEmails } from "../../../api/endpoints/emails";
import { syncDrafts, listDrafts } from "../../../api/endpoints/drafts";
import { toUiError } from "../../../api/client/errors";
import type { EmailMetadataOut, AccountOut, DraftOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

export type AccountTab = "ALL_MAIL" | "SENT" | "SPAM" | "TRASH" | "DRAFTS";

type UseAccountInboxReturn = {
  emails: EmailMetadataOut[];
  drafts: DraftOut[];
  accounts: AccountOut[];
  activeTab: AccountTab;
  setActiveTab: (tab: AccountTab) => void;
  isDraftsTab: boolean;
  loading: boolean;
  error: UiError | null;
};

export default function useAccountInbox(
  mailboxId: string,
  accountId: string,
): UseAccountInboxReturn {
  const [activeTab, setActiveTab] = useState<AccountTab>("ALL_MAIL");
  const [emails, setEmails] = useState<EmailMetadataOut[]>([]);
  const [drafts, setDrafts] = useState<DraftOut[]>([]);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UiError | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const accountList = await listAccounts(mailboxId);
        if (cancelled) return;
        setAccounts(accountList);

        if (activeTab === "DRAFTS") {
          // Step 1: show cached drafts
          const cached = await listDrafts(mailboxId, accountId);
          if (cancelled) return;
          setDrafts(cached);
          setEmails([]);
          setLoading(false);

          // Step 2: sync then refresh
          await syncDrafts(mailboxId, accountId).catch(() => {});
          if (cancelled) return;
          const fresh = await listDrafts(mailboxId, accountId);
          if (!cancelled) setDrafts(fresh);
        } else {
          // Step 1: show cached emails
          const cached = await listEmails(mailboxId, activeTab, accountId);
          if (cancelled) return;
          setEmails(cached);
          setDrafts([]);
          setLoading(false);

          // Step 2: sync then refresh
          await syncEmailMetadata(mailboxId, accountId).catch(() => {});
          if (cancelled) return;
          const fresh = await listEmails(mailboxId, activeTab, accountId);
          if (!cancelled) setEmails(fresh);
        }
      } catch (err) {
        if (!cancelled) {
          setError(toUiError(err));
          setLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [mailboxId, accountId, activeTab]);

  return {
    emails,
    drafts,
    accounts,
    activeTab,
    setActiveTab,
    isDraftsTab: activeTab === "DRAFTS",
    loading,
    error,
  };
}
