import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { RefreshCw, Plus } from 'lucide-react';

import { buildAccountMap, formatShortDate, resolveAccount } from '../../../lib/formatters';
import Spinner from '../../../components/common/Spinner';
import Checkbox from '../../../components/common/Checkbox';
import type { HeaderCheckboxState } from '../../../lib/hooks/useSelection';
import type { DraftOut, AccountOut } from '../../../api/types/dto';

type Props = {
  drafts: DraftOut[];
  accounts: AccountOut[];
  loading: boolean;
  syncing?: boolean;
  onSync?: () => void;
  onNewDraft?: () => void;
  onRowClick?: (draft: DraftOut) => void;
  hasSelection?: boolean;
  isSelected?: (draft: DraftOut) => boolean;
  onToggle?: (draft: DraftOut) => void;
  onToggleAll?: () => void;
  headerCheckboxState?: HeaderCheckboxState;
  bulkBar?: ReactNode;
};

export default function DraftsTable({
  drafts,
  accounts,
  loading,
  syncing = false,
  onSync,
  onNewDraft,
  onRowClick,
  hasSelection = false,
  isSelected,
  onToggle,
  onToggleAll,
  headerCheckboxState = 'unchecked',
  bulkBar,
}: Props) {
  const accountsById = useMemo(() => buildAccountMap(accounts), [accounts]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const selectionEnabled = Boolean(isSelected && onToggle && onToggleAll);

  return (
    <div className="flex flex-col">
      <div className="flex h-11 items-center gap-4 border-b border-zinc-200 px-8">
        {hasSelection && bulkBar ? (
          bulkBar
        ) : (
          <>
            {selectionEnabled ? (
              <Checkbox
                state={headerCheckboxState}
                onClick={onToggleAll!}
                ariaLabel="Seleccionar los 50 borradores más recientes"
              />
            ) : (
              <div className="h-[18px] w-[18px] rounded border-[1.5px] border-zinc-300" />
            )}
            {onSync ? (
              <button
                type="button"
                onClick={onSync}
                disabled={syncing}
                className="flex items-center gap-1.5 rounded px-2 py-1 text-[13px] font-medium text-zinc-600 transition-colors hover:bg-zinc-100 disabled:opacity-50"
                aria-label="Sincronizar borradores"
              >
                <RefreshCw className={`h-[18px] w-[18px] ${syncing ? 'animate-spin' : ''}`} />
                Sincronizar
              </button>
            ) : (
              <RefreshCw className="h-[18px] w-[18px] text-zinc-500" />
            )}
            {onNewDraft && (
              <button
                type="button"
                onClick={onNewDraft}
                className="flex items-center gap-1.5 rounded px-2 py-1 text-[13px] font-medium text-blue-600 transition-colors hover:bg-blue-50"
              >
                <Plus className="h-[18px] w-[18px]" />
                Nuevo borrador
              </button>
            )}
            <span className="text-[13px] font-medium text-zinc-500">
              {drafts.length} borradores
            </span>
          </>
        )}
      </div>

      <div className="flex h-8 items-center gap-3 border-b border-zinc-200 px-8 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
        <div className="w-[18px]" />
        <div className="w-[120px]">Remitente</div>
        <div className="w-[170px]">Para</div>
        <div className="w-[170px]">De</div>
        <div className="flex-1">Asunto</div>
        <div className="w-16 text-right">Fecha</div>
      </div>

      {drafts.length === 0 ? (
        <div className="py-16 text-center text-sm text-zinc-400">No hay borradores guardados</div>
      ) : (
        drafts.map((draft) => {
          const { providerName, accountEmail } = resolveAccount(draft.account_id, accountsById);
          const toDisplay =
            draft.to_recipients.length > 0 ? draft.to_recipients[0] : '(Sin destinatario)';
          const checked = isSelected?.(draft) ?? false;
          const rowBg = checked ? 'bg-blue-50' : 'bg-white';
          const clickable = Boolean(onRowClick);

          return (
            <div
              key={`${draft.provider_draft_id}-${draft.account_id}`}
              onClick={clickable ? () => onRowClick!(draft) : undefined}
              className={`flex h-11 items-center gap-3 border-b border-zinc-100 px-8 ${rowBg} ${
                clickable ? 'cursor-pointer hover:bg-zinc-50' : ''
              }`}
            >
              {selectionEnabled ? (
                <Checkbox
                  state={checked ? 'checked' : 'unchecked'}
                  onClick={() => onToggle!(draft)}
                  ariaLabel="Seleccionar borrador"
                />
              ) : (
                <div className="h-[18px] w-[18px] rounded border-[1.5px] border-zinc-300" />
              )}
              <div className="w-[120px] truncate text-[13px] text-zinc-900">{providerName}</div>
              <div className="w-[170px] truncate text-xs text-zinc-900">{toDisplay}</div>
              <div className="w-[170px] truncate text-xs text-zinc-900">{accountEmail}</div>
              <div className="flex-1 truncate text-[13px] text-zinc-900">
                {draft.subject || '(Sin asunto)'}
              </div>
              <div className="w-16 text-right text-xs text-zinc-900">
                {formatShortDate(draft.updated_at)}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
