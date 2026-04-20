import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import {
  markAsSpam,
  moveToTrash,
  restoreFromSpam,
  trashAction,
  updateReadStatus,
} from '../../../api/endpoints/emails';
import { toUiError } from '../../../api/client/errors';
import type { EmailItemRef } from '../../../api/types/dto';
import type { UiError } from '../../../api/client/errors';

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
  trashActionItems: (items: EmailItemRef[], action: 'delete' | 'restore') => Promise<void>;
};

export default function useEmailBulkActions({
  mailboxId,
  refresh,
  clearSelection,
}: Params): UseEmailBulkActionsReturn {
  const queryClient = useQueryClient();

  const invalidate = useCallback(() => {
    return queryClient.invalidateQueries({ queryKey: ['emails', mailboxId] });
  }, [queryClient, mailboxId]);

  const sharedOnSuccess = useCallback(async () => {
    clearSelection();
    await invalidate();
    await refresh();
  }, [clearSelection, invalidate, refresh]);

  const moveToTrashMut = useMutation({
    mutationFn: (items: EmailItemRef[]) => moveToTrash(mailboxId, items),
    onSuccess: sharedOnSuccess,
  });

  const readStatusMut = useMutation({
    mutationFn: ({ items, isRead }: { items: EmailItemRef[]; isRead: boolean }) =>
      updateReadStatus(mailboxId, isRead, items),
    onSuccess: sharedOnSuccess,
  });

  const spamMut = useMutation({
    mutationFn: (items: EmailItemRef[]) => markAsSpam(mailboxId, items),
    onSuccess: sharedOnSuccess,
  });

  const restoreSpamMut = useMutation({
    mutationFn: (items: EmailItemRef[]) => restoreFromSpam(mailboxId, items),
    onSuccess: sharedOnSuccess,
  });

  const trashActionMut = useMutation({
    mutationFn: ({ items, action }: { items: EmailItemRef[]; action: 'delete' | 'restore' }) =>
      trashAction(mailboxId, action, items),
    onSuccess: sharedOnSuccess,
  });

  const loading =
    moveToTrashMut.isPending ||
    readStatusMut.isPending ||
    spamMut.isPending ||
    restoreSpamMut.isPending ||
    trashActionMut.isPending;

  const firstError =
    moveToTrashMut.error ||
    readStatusMut.error ||
    spamMut.error ||
    restoreSpamMut.error ||
    trashActionMut.error;
  const error = firstError ? toUiError(firstError) : null;

  const moveToTrashItems = useCallback(
    async (items: EmailItemRef[]) => {
      await moveToTrashMut.mutateAsync(items).catch(() => undefined);
    },
    [moveToTrashMut],
  );

  const setReadStatusItems = useCallback(
    async (items: EmailItemRef[], isRead: boolean) => {
      await readStatusMut.mutateAsync({ items, isRead }).catch(() => undefined);
    },
    [readStatusMut],
  );

  const spamItems = useCallback(
    async (items: EmailItemRef[]) => {
      await spamMut.mutateAsync(items).catch(() => undefined);
    },
    [spamMut],
  );

  const restoreFromSpamItems = useCallback(
    async (items: EmailItemRef[]) => {
      await restoreSpamMut.mutateAsync(items).catch(() => undefined);
    },
    [restoreSpamMut],
  );

  const trashActionItems = useCallback(
    async (items: EmailItemRef[], action: 'delete' | 'restore') => {
      await trashActionMut.mutateAsync({ items, action }).catch(() => undefined);
    },
    [trashActionMut],
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
