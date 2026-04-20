import { useCallback, useMemo } from 'react';
import type { ReactNode } from 'react';

import useSelection from '../../../lib/hooks/useSelection';
import useEmailBulkActions from './useEmailBulkActions';
import BulkActionsBar from '../components/BulkActionsBar';
import type { BulkAction, ReadToggleTarget } from '../types';
import type { EmailBox } from '../../../lib/types';
import type { EmailMetadataOut, EmailItemRef } from '../../../api/types/dto';
import type { UiError } from '../../../api/client/errors';

function toItem(e: EmailMetadataOut): EmailItemRef {
  return { account_id: e.account_id, provider_message_id: e.provider_message_id };
}

function emailKey(e: EmailMetadataOut): string {
  return `${e.account_id}|${e.provider_message_id}`;
}

type UseBulkBarArgs = {
  mailboxId: string;
  box: EmailBox;
  emails: EmailMetadataOut[];
  refresh: () => Promise<void>;
};

type UseBulkBarReturn = {
  selection: ReturnType<typeof useSelection<EmailMetadataOut>>;
  bulkError: UiError | null;
  bulkBar: ReactNode;
};

export default function useBulkBar({
  mailboxId,
  box,
  emails,
  refresh,
}: UseBulkBarArgs): UseBulkBarReturn {
  const selection = useSelection<EmailMetadataOut>(emailKey);
  const bulk = useEmailBulkActions({
    mailboxId,
    refresh,
    clearSelection: selection.clear,
  });

  const { selected, items, readToggleTarget } = useMemo(() => {
    const sel = selection.getSelected(emails);
    let readCount = 0;
    for (const e of sel) if (e.is_read) readCount++;
    const unreadCount = sel.length - readCount;
    const target: ReadToggleTarget = unreadCount >= readCount ? 'mark_read' : 'mark_unread';
    return { selected: sel, items: sel.map(toItem), readToggleTarget: target };
  }, [emails, selection]);

  const onAction = useCallback(
    (action: BulkAction) => {
      switch (action) {
        case 'toggle_read':
          return bulk.setReadStatusItems(items, readToggleTarget === 'mark_read');
        case 'move_to_trash':
          return bulk.moveToTrashItems(items);
        case 'mark_spam':
          return bulk.spamItems(items);
        case 'restore_from_spam':
          return bulk.restoreFromSpamItems(items);
        case 'delete_permanently':
          return bulk.trashActionItems(items, 'delete');
        case 'restore_from_trash':
          return bulk.trashActionItems(items, 'restore');
      }
    },
    [bulk, items, readToggleTarget],
  );

  const bulkBar = (
    <BulkActionsBar
      selectedCount={selected.length}
      box={box}
      readToggleTarget={readToggleTarget}
      disabled={bulk.loading}
      onClear={selection.clear}
      onAction={onAction}
    />
  );

  return { selection, bulkError: bulk.error, bulkBar };
}
