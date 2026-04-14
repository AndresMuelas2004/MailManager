import { useCallback, useEffect, useState } from "react";

import { listAccounts, createAccount, connectAccount } from "../../../api/endpoints/accounts";
import { syncEmailMetadata, listEmails } from "../../../api/endpoints/emails";
import { syncDrafts } from "../../../api/endpoints/drafts";
import { toUiError } from "../../../api/client/errors";
import type { AccountOut, EmailMetadataOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

export type AccountEntry = {
  account: AccountOut;
  emails: EmailMetadataOut[];
  status: "syncing" | "ready" | "error";
};

type UseConnectedAccountsReturn = {
  entries: AccountEntry[];
  loading: boolean;
  displayLabel: string;
  setDisplayLabel: (v: string) => void;
  selectedProvider: string;
  setSelectedProvider: (v: string) => void;
  canAdd: boolean;
  addingAccount: boolean;
  addAccount: () => Promise<void>;
  error: UiError | null;
};

export default function useConnectedAccounts(mailboxId: string): UseConnectedAccountsReturn {
  const [entries, setEntries] = useState<AccountEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [displayLabel, setDisplayLabel] = useState("");
  const [selectedProvider, setSelectedProvider] = useState("");
  const [addingAccount, setAddingAccount] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const canAdd = selectedProvider.length > 0 && !addingAccount;

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const accounts = await listAccounts(mailboxId);
        if (cancelled) return;

        const initialEntries: AccountEntry[] = accounts.map((a) => ({
          account: a,
          emails: [],
          status: "syncing" as const,
        }));
        setEntries(initialEntries);
        setLoading(false);

        for (const account of accounts) {
          try {
            const emails = await listEmails(mailboxId, "ALL_MAIL", account.account_id);
            if (cancelled) return;
            setEntries((prev) =>
              prev.map((e) =>
                e.account.account_id === account.account_id
                  ? { ...e, emails: emails.slice(0, 3), status: "ready" as const }
                  : e,
              ),
            );
          } catch {
            if (cancelled) return;
            setEntries((prev) =>
              prev.map((e) =>
                e.account.account_id === account.account_id
                  ? { ...e, status: "ready" as const }
                  : e,
              ),
            );
          }
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [mailboxId]);

  const addAccount = useCallback(async () => {
    if (!canAdd) return;
    setError(null);
    setAddingAccount(true);

    const providerLabel = selectedProvider === "gmail" ? "Gmail" : "Outlook";
    const label = displayLabel.trim() || providerLabel;

    try {
      const account = await createAccount(mailboxId, {
        provider: selectedProvider,
        display_label: label,
      });

      const newEntry: AccountEntry = { account, emails: [], status: "syncing" };
      setEntries((prev) => [...prev, newEntry]);
      setSelectedProvider("");
      setDisplayLabel("");

      await connectAccount(mailboxId, account.account_id);

      const accounts = await listAccounts(mailboxId);
      const updatedAccount = accounts.find((a) => a.account_id === account.account_id);
      if (updatedAccount) {
        setEntries((prev) =>
          prev.map((e) =>
            e.account.account_id === account.account_id
              ? { ...e, account: updatedAccount }
              : e,
          ),
        );
      }

      const [syncResult] = await Promise.all([
        syncEmailMetadata(mailboxId, account.account_id),
        syncDrafts(mailboxId, account.account_id).catch(() => {}),
      ]);

      if (syncResult.total_synced > 0) {
        const emails = await listEmails(mailboxId, "ALL_MAIL", account.account_id);
        setEntries((prev) =>
          prev.map((e) =>
            e.account.account_id === account.account_id
              ? { ...e, emails: emails.slice(0, 3), status: "ready" }
              : e,
          ),
        );
      } else {
        setEntries((prev) =>
          prev.map((e) =>
            e.account.account_id === account.account_id
              ? { ...e, status: "ready" }
              : e,
          ),
        );
      }
    } catch (err) {
      setError(toUiError(err));
      setEntries((prev) => {
        const last = prev[prev.length - 1];
        if (last?.status === "syncing") {
          return [...prev.slice(0, -1), { ...last, status: "error" as const }];
        }
        return prev;
      });
    } finally {
      setAddingAccount(false);
    }
  }, [canAdd, mailboxId, selectedProvider, displayLabel]);

  return {
    entries,
    loading,
    displayLabel,
    setDisplayLabel,
    selectedProvider,
    setSelectedProvider,
    canAdd,
    addingAccount,
    addAccount,
    error,
  };
}
