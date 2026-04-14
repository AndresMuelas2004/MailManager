import { useCallback, useState } from "react";

import { createMailbox } from "../../../api/endpoints/mailboxes";
import { toUiError } from "../../../api/client/errors";
import type { UiError } from "../../../api/client/errors";
import type { MailboxOut } from "../../../api/types/dto";

type UseCreateMailboxReturn = {
  displayName: string;
  setDisplayName: (value: string) => void;
  canSubmit: boolean;
  loading: boolean;
  error: UiError | null;
  createdMailbox: MailboxOut | null;
  handleCreate: () => Promise<void>;
};

export default function useCreateMailbox(): UseCreateMailboxReturn {
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UiError | null>(null);
  const [createdMailbox, setCreatedMailbox] = useState<MailboxOut | null>(null);

  const canSubmit = displayName.trim().length > 0 && !loading;

  const handleCreate = useCallback(async () => {
    const trimmed = displayName.trim();
    if (trimmed.length === 0) return;

    setError(null);
    setLoading(true);
    try {
      const mailbox = await createMailbox({ display_name: trimmed });
      setCreatedMailbox(mailbox);
    } catch (err) {
      setError(toUiError(err));
    } finally {
      setLoading(false);
    }
  }, [displayName]);

  return {
    displayName,
    setDisplayName,
    canSubmit,
    loading,
    error,
    createdMailbox,
    handleCreate,
  };
}
