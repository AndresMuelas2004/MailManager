import { useCallback, useState } from "react";

import { listAccounts } from "../../../api/endpoints/accounts";
import type { AccountOut, DraftOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";
import type { ComposerMode } from "../../../lib/types";
import useComposerForm from "./useComposerForm";
import useDraftPersistence from "./useDraftPersistence";

type OpenNewDraftArgs = {
  accountId?: string;
};

type UseDraftComposerReturn = {
  open: boolean;
  mode: ComposerMode | null;
  accounts: AccountOut[];
  accountId: string;
  setAccountId: (id: string) => void;
  to: string;
  setTo: (v: string) => void;
  cc: string;
  setCc: (v: string) => void;
  bcc: string;
  setBcc: (v: string) => void;
  subject: string;
  setSubject: (v: string) => void;
  body: string;
  setBody: (v: string) => void;
  sending: boolean;
  saving: boolean;
  error: UiError | null;
  canSendEmail: boolean;
  canSaveDraft: boolean;
  canSendDraft: boolean;
  openForNewEmail: () => void;
  openForNewDraft: (args?: OpenNewDraftArgs) => void;
  openForEditDraft: (draft: DraftOut) => void;
  closeWithX: () => void;
  handleSendEmail: () => Promise<void>;
  handleSaveDraft: () => Promise<void>;
  handleSendDraft: () => Promise<void>;
  setRefreshCallback: (fn: (() => void | Promise<void>) | null) => void;
};

export default function useDraftComposer(
  mailboxId: string | null,
): UseDraftComposerReturn {
  const [mode, setMode] = useState<ComposerMode | null>(null);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [providerDraftId, setProviderDraftIdState] = useState<string | null>(null);
  const [refreshCallback, setRefreshCallbackState] = useState<
    (() => void | Promise<void>) | null
  >(null);
  const form = useComposerForm();
  const persistence = useDraftPersistence();

  const setRefreshCallback = useCallback(
    (fn: (() => void | Promise<void>) | null) => {
      setRefreshCallbackState(() => fn);
    },
    [],
  );

  const triggerRefresh = useCallback(async () => {
    if (refreshCallback) {
      try {
        await refreshCallback();
      } catch {
        // refresh failures are non-fatal for the composer flow
      }
    }
  }, [refreshCallback]);

  const resetAll = useCallback(() => {
    form.reset();
    persistence.setError(null);
    persistence.setProviderDraftId(null);
    setProviderDraftIdState(null);
  }, [form, persistence]);

  const loadAccountsIfNeeded = useCallback(async () => {
    if (!mailboxId) return accounts;
    if (accounts.length > 0) return accounts;
    try {
      const accs = await listAccounts(mailboxId);
      setAccounts(accs);
      return accs;
    } catch {
      return [] as AccountOut[];
    }
  }, [accounts, mailboxId]);

  const openForNewEmail = useCallback(() => {
    if (!mailboxId) return;
    resetAll();
    setMode("new_email");
    loadAccountsIfNeeded().then((accs) => {
      if (accs.length > 0 && !form.accountId) {
        form.setAccountId(accs[0].account_id);
      }
    });
  }, [form, loadAccountsIfNeeded, mailboxId, resetAll]);

  const openForNewDraft = useCallback(
    (args?: OpenNewDraftArgs) => {
      if (!mailboxId) return;
      resetAll();
      setMode("new_draft");
      const preset = args?.accountId;
      loadAccountsIfNeeded().then((accs) => {
        if (preset && accs.some((a) => a.account_id === preset)) {
          form.setAccountId(preset);
        } else if (accs.length > 0) {
          form.setAccountId(accs[0].account_id);
        }
      });
    },
    [form, loadAccountsIfNeeded, mailboxId, resetAll],
  );

  const openForEditDraft = useCallback(
    (draft: DraftOut) => {
      if (!mailboxId) return;
      resetAll();
      setMode("edit_draft");
      form.seedFromDraft(draft);
      setProviderDraftIdState(draft.provider_draft_id);
      persistence.setProviderDraftId(draft.provider_draft_id);
      loadAccountsIfNeeded();
    },
    [form, loadAccountsIfNeeded, mailboxId, persistence, resetAll],
  );

  const close = useCallback(() => {
    setMode(null);
    resetAll();
  }, [resetAll]);

  const handleSendEmail = useCallback(async () => {
    if (!mailboxId || !form.accountId) return;
    const recipients = form.parseRecipients(form.to);
    if (recipients.length === 0) return;
    const ok = await persistence.sendEmailNow(
      mailboxId,
      form.accountId,
      recipients,
      form.subject,
      form.body,
    );
    if (ok) {
      close();
      await triggerRefresh();
    }
  }, [close, form, mailboxId, persistence, triggerRefresh]);

  const handleSaveDraft = useCallback(async () => {
    if (!mailboxId || !form.accountId) return;
    const ok = await persistence.saveDraftNow(
      mailboxId,
      form.accountId,
      form.buildDraftPayload(),
    );
    if (ok) {
      close();
      await triggerRefresh();
    }
  }, [close, form, mailboxId, persistence, triggerRefresh]);

  const handleSendDraft = useCallback(async () => {
    if (!mailboxId || !form.accountId) return;
    if (!providerDraftId) return;
    const payloadIfDirty = form.isDirty() ? form.buildDraftPayload() : null;
    const ok = await persistence.sendDraftNow(
      mailboxId,
      form.accountId,
      providerDraftId,
      payloadIfDirty,
    );
    if (ok) {
      close();
      await triggerRefresh();
    }
  }, [close, form, mailboxId, persistence, providerDraftId, triggerRefresh]);

  const closeWithX = useCallback(() => {
    const currentMode = mode;
    const currentAccountId = form.accountId;

    const shouldPersist =
      (currentMode === "new_email" || currentMode === "new_draft")
        ? form.hasAnyContent()
        : currentMode === "edit_draft"
          ? form.isDirty()
          : false;

    if (shouldPersist && currentAccountId && mailboxId) {
      persistence
        .persistDraft(mailboxId, currentAccountId, form.buildDraftPayload())
        .then(() => triggerRefresh())
        .catch(() => {});
    }
    close();
  }, [close, form, mailboxId, mode, persistence, triggerRefresh]);

  const canSendEmail =
    mode === "new_email" &&
    form.accountId.length > 0 &&
    form.parseRecipients(form.to).length > 0 &&
    !persistence.sending;

  const canSaveDraft =
    (mode === "new_draft" || mode === "edit_draft") &&
    form.accountId.length > 0 &&
    !persistence.saving;

  const canSendDraft =
    mode === "edit_draft" &&
    form.accountId.length > 0 &&
    providerDraftId !== null &&
    form.parseRecipients(form.to).length > 0 &&
    !persistence.sending;

  return {
    open: mode !== null,
    mode,
    accounts,
    accountId: form.accountId,
    setAccountId: form.setAccountId,
    to: form.to,
    setTo: form.setTo,
    cc: form.cc,
    setCc: form.setCc,
    bcc: form.bcc,
    setBcc: form.setBcc,
    subject: form.subject,
    setSubject: form.setSubject,
    body: form.body,
    setBody: form.setBody,
    sending: persistence.sending,
    saving: persistence.saving,
    error: persistence.error,
    canSendEmail,
    canSaveDraft,
    canSendDraft,
    openForNewEmail,
    openForNewDraft,
    openForEditDraft,
    closeWithX,
    handleSendEmail,
    handleSaveDraft,
    handleSendDraft,
    setRefreshCallback,
  };
}
