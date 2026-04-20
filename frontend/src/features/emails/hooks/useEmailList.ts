import { useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { listEmails, syncEmailMetadata } from '../../../api/endpoints/emails';
import { listAccounts } from '../../../api/endpoints/accounts';
import { toUiError } from '../../../api/client/errors';
import type { AccountOut, EmailMetadataOut } from '../../../api/types/dto';
import type { UiError } from '../../../api/client/errors';
import type { EmailBox } from '../../../lib/types';

type UseEmailListReturn = {
  emails: EmailMetadataOut[];
  accounts: AccountOut[];
  loading: boolean;
  syncing: boolean;
  error: UiError | null;
  refresh: () => Promise<void>;
};

export default function useEmailList(
  mailboxId: string,
  box: EmailBox,
  accountId?: string,
): UseEmailListReturn {
  const queryClient = useQueryClient();
  const emailsKey = ['emails', mailboxId, box, accountId ?? null] as const;
  const accountsKey = ['accounts', mailboxId] as const;

  const emailsQuery = useQuery({
    queryKey: emailsKey,
    queryFn: () => listEmails(mailboxId, box, accountId),
    enabled: mailboxId.length > 0,
  });

  const accountsQuery = useQuery({
    queryKey: accountsKey,
    queryFn: () => listAccounts(mailboxId),
    enabled: mailboxId.length > 0,
  });

  const syncMutation = useMutation({
    mutationFn: () => syncEmailMetadata(mailboxId, accountId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['emails', mailboxId] }),
  });

  useEffect(() => {
    if (mailboxId.length === 0) return;
    syncMutation.mutate();
    // syncMutation identity is stable per TanStack Query docs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mailboxId, accountId]);

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: emailsKey });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient, mailboxId, box, accountId]);

  const error = emailsQuery.error
    ? toUiError(emailsQuery.error)
    : accountsQuery.error
      ? toUiError(accountsQuery.error)
      : null;

  return {
    emails: emailsQuery.data ?? [],
    accounts: accountsQuery.data ?? [],
    loading: emailsQuery.isLoading || accountsQuery.isLoading,
    syncing: syncMutation.isPending || (emailsQuery.isFetching && !emailsQuery.isLoading),
    error,
    refresh,
  };
}
