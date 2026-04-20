import { useCallback, useState } from 'react';

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const deleteMany = useCallback(
    async (items: DraftRef[]) => {
      if (items.length === 0) return;
      const confirmMsg =
        items.length > 1
          ? `¿Eliminar ${items.length} borradores? Esta acción no se puede deshacer.`
          : '¿Eliminar este borrador? Esta acción no se puede deshacer.';
      if (!window.confirm(confirmMsg)) return;

      setLoading(true);
      setError(null);
      try {
        const results = await Promise.allSettled(
          items.map((i) => deleteDraft(mailboxId, i.account_id, i.provider_draft_id)),
        );
        const failed = results.filter((r) => r.status === 'rejected');
        if (failed.length > 0) {
          const firstFailure = failed[0] as PromiseRejectedResult;
          const base = toUiError(firstFailure.reason);
          setError({
            code: base.code ?? 'partial_delete',
            message:
              failed.length === items.length
                ? `No se pudieron eliminar los borradores: ${base.message}`
                : `${failed.length} de ${items.length} borradores no se pudieron eliminar`,
          });
        }
        clearSelection();
        await refresh();
      } catch (err) {
        setError(toUiError(err));
      } finally {
        setLoading(false);
      }
    },
    [mailboxId, refresh, clearSelection],
  );

  return { loading, error, deleteMany };
}
