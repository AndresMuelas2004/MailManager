import { useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';

import { useDraftComposerContext } from '../../../app/providers/DraftComposerContext';
import useDraftsList from '../hooks/useDraftsList';
import useDraftBulkDelete from '../hooks/useDraftBulkDelete';
import DraftsTable from '../components/DraftsTable';
import DraftBulkActionsBar from '../components/DraftBulkActionsBar';
import useSelection from '../../../lib/hooks/useSelection';
import type { DraftRef } from '../types';
import type { DraftOut } from '../../../api/types/dto';

function draftKey(d: DraftOut): string {
  return `${d.account_id}|${d.provider_draft_id}`;
}

export default function DraftsPage() {
  const { mailboxId } = useParams<{ mailboxId: string }>();
  const { drafts, accounts, loading, syncing, error, refresh, syncAndRefresh } = useDraftsList(
    mailboxId!,
  );

  const selection = useSelection<DraftOut>(draftKey);
  const composer = useDraftComposerContext();

  const bulk = useDraftBulkDelete({
    mailboxId: mailboxId!,
    refresh,
    clearSelection: selection.clear,
  });

  useEffect(() => {
    composer.setRefreshCallback(refresh);
    return () => composer.setRefreshCallback(null);
  }, [composer, refresh]);

  const selectedItems: DraftRef[] = useMemo(
    () =>
      selection.getSelected(drafts).map((d) => ({
        account_id: d.account_id,
        provider_draft_id: d.provider_draft_id,
      })),
    [drafts, selection],
  );

  const bulkBar = (
    <DraftBulkActionsBar
      selectedCount={selectedItems.length}
      disabled={bulk.loading}
      onClear={selection.clear}
      onDelete={() => bulk.deleteMany(selectedItems)}
    />
  );

  const combinedError = error || bulk.error;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-6">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">Borradores</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">
          Borradores guardados de tus cuentas conectadas.
        </p>
      </div>

      {combinedError && (
        <div className="px-8 pb-2 text-sm text-red-600">{combinedError.message}</div>
      )}

      <DraftsTable
        drafts={drafts}
        accounts={accounts}
        loading={loading}
        syncing={syncing}
        onSync={syncAndRefresh}
        onNewDraft={() => composer.openForNewDraft()}
        onRowClick={(draft) => composer.openForEditDraft(draft)}
        hasSelection={selection.size > 0}
        isSelected={selection.isSelected}
        onToggle={selection.toggle}
        onToggleAll={() => selection.toggleTopN(drafts)}
        headerCheckboxState={selection.headerState(drafts)}
        bulkBar={bulkBar}
      />
    </div>
  );
}
