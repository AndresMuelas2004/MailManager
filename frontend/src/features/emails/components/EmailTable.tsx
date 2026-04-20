import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';

import { buildAccountMap, formatDate, resolveAccount } from '../../../lib/formatters';
import Spinner from '../../../components/common/Spinner';
import Checkbox from '../../../components/common/Checkbox';
import type { HeaderCheckboxState } from '../../../lib/hooks/useSelection';
import type { EmailMetadataOut, AccountOut } from '../../../api/types/dto';

type Props = {
  emails: EmailMetadataOut[];
  accounts: AccountOut[];
  loading: boolean;
  hasSelection?: boolean;
  isSelected?: (email: EmailMetadataOut) => boolean;
  onToggle?: (email: EmailMetadataOut) => void;
  onToggleAll?: () => void;
  onOpen?: (email: EmailMetadataOut) => void;
  headerCheckboxState?: HeaderCheckboxState;
  bulkBar?: ReactNode;
};

export default function EmailTable({
  emails,
  accounts,
  loading,
  hasSelection = false,
  isSelected,
  onToggle,
  onToggleAll,
  onOpen,
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
                ariaLabel="Seleccionar los 50 correos más recientes"
              />
            ) : (
              <div className="h-[18px] w-[18px] rounded border-[1.5px] border-zinc-300" />
            )}
            <RefreshCw className="h-[18px] w-[18px] text-zinc-500" />
            <span className="text-[13px] font-medium text-zinc-500">{emails.length} correos</span>
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

      {emails.length === 0 ? (
        <div className="py-16 text-center text-sm text-zinc-400">
          No hay correos en esta bandeja
        </div>
      ) : (
        emails.map((email) => {
          const { providerName, accountEmail } = resolveAccount(email.account_id, accountsById);
          const unread = !email.is_read;
          const weight = unread ? 'font-semibold' : 'font-normal';
          const checked = isSelected?.(email) ?? false;
          const rowBg = checked ? 'bg-blue-50' : unread ? 'bg-zinc-200' : 'bg-white';

          const openable = Boolean(onOpen);
          return (
            <div
              key={`${email.account_id}|${email.provider_message_id}`}
              role={openable ? 'button' : undefined}
              tabIndex={openable ? 0 : undefined}
              onClick={openable ? () => onOpen!(email) : undefined}
              onKeyDown={
                openable
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onOpen!(email);
                      }
                    }
                  : undefined
              }
              className={`flex h-11 items-center gap-3 border-b border-zinc-100 px-8 ${rowBg} ${openable ? 'cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600' : ''}`}
            >
              {selectionEnabled ? (
                <Checkbox
                  state={checked ? 'checked' : 'unchecked'}
                  onClick={() => onToggle!(email)}
                  ariaLabel="Seleccionar correo"
                />
              ) : (
                <div className="h-[18px] w-[18px] rounded border-[1.5px] border-zinc-300" />
              )}
              <div className={`w-[120px] truncate text-[13px] ${weight} text-zinc-900`}>
                {providerName}
              </div>
              <div className={`w-[170px] truncate text-xs ${weight} text-zinc-900`}>
                {accountEmail}
              </div>
              <div className={`w-[170px] truncate text-xs ${weight} text-zinc-900`}>
                {email.from_email}
              </div>
              <div className={`flex-1 truncate text-[13px] ${weight} text-zinc-900`}>
                {email.subject ?? '(Sin asunto)'}
              </div>
              <div className={`w-16 text-right text-xs ${weight} text-zinc-900`}>
                {formatDate(email.received_at)}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
