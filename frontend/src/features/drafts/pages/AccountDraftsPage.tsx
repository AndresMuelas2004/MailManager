import { useEffect, useMemo } from "react";
import { useParams } from "react-router-dom";

import { useDraftComposerContext } from "../../../app/providers/DraftComposerContext";
import useDraftsList from "../hooks/useDraftsList";
import useDraftBulkDelete from "../hooks/useDraftBulkDelete";
import DraftsTable from "../components/DraftsTable";
import DraftBulkActionsBar from "../components/DraftBulkActionsBar";
import AccountTabs from "../../emails/components/AccountTabs";
import useSelection from "../../../lib/hooks/useSelection";
import { isGenericLabel } from "../../../lib/providers";
import type { DraftRef } from "../types";
import type { DraftOut } from "../../../api/types/dto";

function draftKey(d: DraftOut): string {
  return `${d.account_id}|${d.provider_draft_id}`;
}

export default function AccountDraftsPage() {
  const { mailboxId, accountId } = useParams<{
    mailboxId: string;
    accountId: string;
  }>();
  const { drafts, accounts, loading, syncing, error, refresh, syncAndRefresh } =
    useDraftsList(mailboxId!, accountId!);

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

  const { title, bandejaLabel } = useMemo(() => {
    const account = accounts.find((a) => a.account_id === accountId);
    const hasCustomLabel = account
      ? !isGenericLabel(account.display_label, account.provider)
      : false;
    const email = account?.email_address ?? account?.display_label ?? accountId!;
    const computedTitle =
      hasCustomLabel && account ? `${account.display_label} - ${email}` : email;
    const computedBandeja =
      hasCustomLabel && account ? `Bandeja ${account.display_label}` : `Bandeja ${email}`;
    return { title: computedTitle, bandejaLabel: computedBandeja };
  }, [accounts, accountId]);

  const bulkBar = (
    <DraftBulkActionsBar
      selectedCount={selectedItems.length}
      disabled={bulk.loading}
      onClear={selection.clear}
      onDelete={() => bulk.deleteMany(selectedItems)}
    />
  );

  const combinedError = error || bulk.error;
  const basePath = `/m/${mailboxId}/account/${accountId}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-2">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">{title}</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">Borradores de {title}</p>
      </div>

      <AccountTabs basePath={basePath} inboxLabel={bandejaLabel} />

      {combinedError && (
        <div className="px-8 pt-4 text-sm text-red-600">{combinedError.message}</div>
      )}

      <DraftsTable
        drafts={drafts}
        accounts={accounts}
        loading={loading}
        syncing={syncing}
        onSync={syncAndRefresh}
        onNewDraft={() => composer.openForNewDraft({ accountId })}
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
