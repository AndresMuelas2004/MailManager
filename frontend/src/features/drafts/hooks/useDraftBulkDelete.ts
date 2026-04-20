import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { deleteDraft } from '../../../api/endpoints/drafts';
import { toUiError } from '../../../api/client/errors';
import type { UiError } from '../../../api/client/errors';
import type { DraftRef } from '../types';

type Params = {
  mailboxId: string;
  refresh: () => Promise<void>;
  clearSelection: () => void;
};

export type UseDraftBulkDeleteReturn = {
  loading: boolean;
  error: UiError | null;
  deleteMany: (items: DraftRef[]) => Promise<void>;
};

export default function useDraftBulkDelete({
  mailboxId,
  refresh,
  clearSelection,
}: Params): UseDraftBulkDeleteReturn {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (items: DraftRef[]) => {
      const results = await Promise.allSettled(
        items.map((item) => deleteDraft(mailboxId, item.account_id, item.provider_draft_id)),
      );
      const failed = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected');
      return { total: items.length, failed };
    },
    onSuccess: async ({ total, failed }) => {
      if (failed.length > 0) {
        const base = toUiError(failed[0].reason);
        const message =
          failed.length === total
            ? `No se pudieron eliminar los borradores: ${base.message}`
            : `${failed.length} de ${total} borradores no se pudieron eliminar`;
        throw Object.assign(new Error(message), { code: base.code ?? 'partial_delete' });
      }
      clearSelection();
      await queryClient.invalidateQueries({ queryKey: ['drafts', mailboxId] });
      await refresh();
    },
  });

  const deleteMany = useCallback(
    async (items: DraftRef[]) => {
      if (items.length === 0) return;
      const confirmMsg =
        items.length > 1
          ? `¿Eliminar ${items.length} borradores? Esta acción no se puede deshacer.`
          : '¿Eliminar este borrador? Esta acción no se puede deshacer.';
      if (!window.confirm(confirmMsg)) return;
      await mutation.mutateAsync(items).catch(() => undefined);
    },
    [mutation],
  );

  const error = mutation.error ? toUiError(mutation.error) : null;

  return {
    loading: mutation.isPending,
    error,
    deleteMany,
  };
}
