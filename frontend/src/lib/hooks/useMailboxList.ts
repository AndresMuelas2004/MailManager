import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createMailbox, listMailboxes } from '../../api/endpoints/mailboxes';
import type { MailboxOut } from '../../api/types/dto';

export const MAILBOXES_QUERY_KEY = ['mailboxes'] as const;

type UseMailboxListReturn = {
  mailboxes: MailboxOut[];
  currentMailboxName: string;
  handleCreate: (displayName: string) => Promise<MailboxOut | null>;
};

export default function useMailboxList(currentMailboxId: string): UseMailboxListReturn {
  const queryClient = useQueryClient();

  const { data: mailboxes = [] } = useQuery({
    queryKey: MAILBOXES_QUERY_KEY,
    queryFn: listMailboxes,
  });

  const createMutation = useMutation({
    mutationFn: (displayName: string) => createMailbox({ display_name: displayName }),
    onSuccess: (created) => {
      queryClient.setQueryData<MailboxOut[]>(MAILBOXES_QUERY_KEY, (prev) =>
        prev ? [...prev, created] : [created],
      );
    },
  });

  const handleCreate = useCallback(
    async (displayName: string): Promise<MailboxOut | null> => {
      try {
        return await createMutation.mutateAsync(displayName);
      } catch {
        return null;
      }
    },
    [createMutation],
  );

  const currentMailbox = mailboxes.find((m) => m.mailbox_id === currentMailboxId);
  const currentMailboxName = currentMailbox?.display_name ?? '';

  return { mailboxes, currentMailboxName, handleCreate };
}
