import { useCallback, useRef, useState } from 'react';

import { createDraft, updateDraft, sendDraft } from '../../../api/endpoints/drafts';
import { sendEmail } from '../../../api/endpoints/emails';
import { toUiError } from '../../../api/client/errors';
import type { UiError } from '../../../api/client/errors';
import type { DraftPayload } from './useComposerForm';

export type UseDraftPersistenceReturn = {
  sending: boolean;
  saving: boolean;
  error: UiError | null;
  setError: (e: UiError | null) => void;
  providerDraftId: string | null;
  setProviderDraftId: (id: string | null) => void;
  persistDraft: (mailboxId: string, accountId: string, payload: DraftPayload) => Promise<void>;
  sendEmailNow: (
    mailboxId: string,
    accountId: string,
    recipients: string[],
    subject: string,
    body: string,
  ) => Promise<boolean>;
  sendDraftNow: (
    mailboxId: string,
    accountId: string,
    providerDraftId: string,
    payloadIfDirty: DraftPayload | null,
  ) => Promise<boolean>;
  saveDraftNow: (mailboxId: string, accountId: string, payload: DraftPayload) => Promise<boolean>;
};

export default function useDraftPersistence(): UseDraftPersistenceReturn {
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<UiError | null>(null);
  const providerDraftIdRef = useRef<string | null>(null);

  const setProviderDraftId = useCallback((id: string | null) => {
    providerDraftIdRef.current = id;
  }, []);

  const persistDraft = useCallback(
    async (mailboxId: string, accountId: string, payload: DraftPayload) => {
      const existingId = providerDraftIdRef.current;
      if (existingId) {
        await updateDraft(mailboxId, accountId, existingId, payload);
      } else {
        const created = await createDraft(mailboxId, accountId, payload);
        providerDraftIdRef.current = created.provider_draft_id;
      }
    },
    [],
  );

  const sendEmailNow = useCallback(
    async (
      mailboxId: string,
      accountId: string,
      recipients: string[],
      subject: string,
      body: string,
    ): Promise<boolean> => {
      if (sending) return false;
      setError(null);
      setSending(true);
      try {
        await sendEmail(mailboxId, {
          account_id: accountId,
          subject,
          body,
          recipients,
        });
        return true;
      } catch (err) {
        const uiErr = toUiError(err);
        const isRecipientError =
          uiErr.code === 'recipients_missing' || uiErr.code === 'email_send_error';
        setError({
          ...uiErr,
          message: isRecipientError ? 'Destinatario no encontrado' : uiErr.message,
        });
        return false;
      } finally {
        setSending(false);
      }
    },
    [sending],
  );

  const sendDraftNow = useCallback(
    async (
      mailboxId: string,
      accountId: string,
      providerDraftId: string,
      payloadIfDirty: DraftPayload | null,
    ): Promise<boolean> => {
      if (sending) return false;
      setError(null);
      setSending(true);
      try {
        if (payloadIfDirty) {
          await updateDraft(mailboxId, accountId, providerDraftId, payloadIfDirty);
        }
        await sendDraft(mailboxId, accountId, providerDraftId);
        return true;
      } catch (err) {
        setError(toUiError(err));
        return false;
      } finally {
        setSending(false);
      }
    },
    [sending],
  );

  const saveDraftNow = useCallback(
    async (mailboxId: string, accountId: string, payload: DraftPayload): Promise<boolean> => {
      if (saving) return false;
      setError(null);
      setSaving(true);
      try {
        await persistDraft(mailboxId, accountId, payload);
        return true;
      } catch (err) {
        setError(toUiError(err));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [persistDraft, saving],
  );

  return {
    sending,
    saving,
    error,
    setError,
    providerDraftId: providerDraftIdRef.current,
    setProviderDraftId,
    persistDraft,
    sendEmailNow,
    sendDraftNow,
    saveDraftNow,
  };
}
