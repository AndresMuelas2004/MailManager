import { useCallback, useState } from "react";

import {
  moveToTrash,
  updateReadStatus,
  markAsSpam,
  restoreFromSpam,
  trashAction,
} from "../../../api/endpoints/emails";
import { toUiError } from "../../../api/client/errors";
import type { EmailItemRef } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

type Params = {
  mailboxId: string;
  refresh: () => Promise<void>;
  clearSelection: () => void;
};

export type UseEmailBulkActionsReturn = {
  loading: boolean;
  error: UiError | null;
  moveToTrashItems: (items: EmailItemRef[]) => Promise<void>;
  setReadStatusItems: (items: EmailItemRef[], isRead: boolean) => Promise<void>;
  spamItems: (items: EmailItemRef[]) => Promise<void>;
  restoreFromSpamItems: (items: EmailItemRef[]) => Promise<void>;
  trashActionItems: (
    items: EmailItemRef[],
    action: "delete" | "restore",
  ) => Promise<void>;
};

export default function useEmailBulkActions({
  mailboxId,
  refresh,
  clearSelection,
}: Params): UseEmailBulkActionsReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setLoading(true);
      setError(null);
      try {
        await fn();
        clearSelection();
        await refresh();
      } catch (err) {
        setError(toUiError(err));
      } finally {
        setLoading(false);
      }
    },
    [clearSelection, refresh],
  );

  const moveToTrashItems = useCallback(
    (items: EmailItemRef[]) => run(() => moveToTrash(mailboxId, items)),
    [mailboxId, run],
  );

  const setReadStatusItems = useCallback(
    (items: EmailItemRef[], isRead: boolean) =>
      run(() => updateReadStatus(mailboxId, isRead, items)),
    [mailboxId, run],
  );

  const spamItems = useCallback(
    (items: EmailItemRef[]) => run(() => markAsSpam(mailboxId, items)),
    [mailboxId, run],
  );

  const restoreFromSpamItems = useCallback(
    (items: EmailItemRef[]) => run(() => restoreFromSpam(mailboxId, items)),
    [mailboxId, run],
  );

  const trashActionItems = useCallback(
    (items: EmailItemRef[], action: "delete" | "restore") =>
      run(() => trashAction(mailboxId, action, items)),
    [mailboxId, run],
  );

  return {
    loading,
    error,
    moveToTrashItems,
    setReadStatusItems,
    spamItems,
    restoreFromSpamItems,
    trashActionItems,
  };
}
