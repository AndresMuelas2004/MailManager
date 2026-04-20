import { useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { listDrafts, syncDrafts } from '../../../api/endpoints/drafts';
import { listAccounts } from '../../../api/endpoints/accounts';
import { toUiError } from '../../../api/client/errors';
import type { AccountOut, DraftOut } from '../../../api/types/dto';
import type { UiError } from '../../../api/client/errors';

type UseDraftsListReturn = {
  drafts: DraftOut[];
  accounts: AccountOut[];
  loading: boolean;
  syncing: boolean;
  error: UiError | null;
  refresh: () => Promise<void>;
  syncAndRefresh: () => Promise<void>;
};

export default function useDraftsList(mailboxId: string, accountId?: string): UseDraftsListReturn {
  const queryClient = useQueryClient();
  const draftsKey = ['drafts', mailboxId, accountId ?? null] as const;
  const accountsKey = ['accounts', mailboxId] as const;

  const draftsQuery = useQuery({
    queryKey: draftsKey,
    queryFn: () => listDrafts(mailboxId, accountId),
    enabled: mailboxId.length > 0,
  });

  const accountsQuery = useQuery({
    queryKey: accountsKey,
    queryFn: () => listAccounts(mailboxId),
    enabled: mailboxId.length > 0,
  });

  const syncMutation = useMutation({
    mutationFn: () => syncDrafts(mailboxId, accountId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['drafts', mailboxId] }),
  });

  useEffect(() => {
    if (mailboxId.length === 0) return;
    syncMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mailboxId, accountId]);

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: draftsKey });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient, mailboxId, accountId]);

  const syncAndRefresh = useCallback(async () => {
    await syncMutation.mutateAsync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mailboxId, accountId]);

  const error = draftsQuery.error
    ? toUiError(draftsQuery.error)
    : accountsQuery.error
      ? toUiError(accountsQuery.error)
      : syncMutation.error
        ? toUiError(syncMutation.error)
        : null;

  return {
    drafts: draftsQuery.data ?? [],
    accounts: accountsQuery.data ?? [],
    loading: draftsQuery.isLoading || accountsQuery.isLoading,
    syncing: syncMutation.isPending || (draftsQuery.isFetching && !draftsQuery.isLoading),
    error,
    refresh,
    syncAndRefresh,
  };
}
