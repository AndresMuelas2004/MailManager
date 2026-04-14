import { useCallback, useEffect, useState } from "react";

import { listAccounts } from "../../../api/endpoints/accounts";
import { sendEmail } from "../../../api/endpoints/emails";
import { toUiError } from "../../../api/client/errors";
import type { AccountOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

type UseComposeEmailReturn = {
  accounts: AccountOut[];
  selectedAccountId: string;
  setSelectedAccountId: (id: string) => void;
  to: string;
  setTo: (v: string) => void;
  subject: string;
  setSubject: (v: string) => void;
  body: string;
  setBody: (v: string) => void;
  canSend: boolean;
  sending: boolean;
  error: UiError | null;
  handleSend: () => Promise<void>;
};

export default function useComposeEmail(
  mailboxId: string,
  onSuccess: () => void,
): UseComposeEmailReturn {
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAccounts(mailboxId)
      .then((accs) => {
        if (cancelled) return;
        setAccounts(accs);
        if (accs.length > 0) setSelectedAccountId(accs[0].account_id);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [mailboxId]);

  const canSend = to.trim().length > 0 && selectedAccountId.length > 0 && !sending;

  const handleSend = useCallback(async () => {
    if (!canSend) return;
    setError(null);
    setSending(true);
    try {
      await sendEmail(mailboxId, {
        account_id: selectedAccountId,
        subject,
        body,
        recipients: to.split(",").map((r) => r.trim()).filter(Boolean),
      });
      onSuccess();
    } catch (err) {
      const uiErr = toUiError(err);
      const isRecipientError = uiErr.code === "recipients_missing" || uiErr.code === "email_send_error";
      setError({
        ...uiErr,
        message: isRecipientError ? "Destinatario no encontrado" : uiErr.message,
      });
    } finally {
      setSending(false);
    }
  }, [canSend, mailboxId, selectedAccountId, subject, body, to, onSuccess]);

  return {
    accounts,
    selectedAccountId,
    setSelectedAccountId,
    to,
    setTo,
    subject,
    setSubject,
    body,
    setBody,
    canSend,
    sending,
    error,
    handleSend,
  };
}
