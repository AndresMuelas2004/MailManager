import { useEffect, useRef, useState } from 'react';
import { EllipsisVertical, Loader2, Mail } from 'lucide-react';

import { formatShortDate } from '../../../lib/formatters';
import { getProviderMeta, isGenericLabel } from '../../../lib/providers';
import type { AccountOut, EmailMetadataOut } from '../../../api/types/dto';
import AccountCardDropdown from './AccountCardDropdown';

type Props = {
  account: AccountOut;
  emails: EmailMetadataOut[];
  status: 'syncing' | 'ready' | 'error';
  onClick?: () => void;
  onDelete?: () => void;
};

export default function AccountCard({ account, emails, status, onClick, onDelete }: Props) {
  const meta = getProviderMeta(account.provider);
  const headerBg = meta.headerBgClass;
  const headerColor = meta.headerTextClass;

  const hasCustomLabel = !isGenericLabel(account.display_label, account.provider);
  const email = account.email_address;
  const headerText =
    hasCustomLabel && email
      ? `${account.display_label} - ${email}`
      : (email ?? account.display_label);

  const hasActions = !!onDelete;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen]);

  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter') onClick();
            }
          : undefined
      }
      className={`flex w-full flex-col overflow-hidden rounded-2xl border-[1.5px] border-zinc-200 bg-white ${
        onClick ? 'cursor-pointer transition-shadow hover:shadow-md' : ''
      }`}
    >
      <div className={`flex items-center gap-2 px-4 py-3 ${headerBg}`}>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Mail className={`h-3.5 w-3.5 shrink-0 ${headerColor}`} />
          <span className={`truncate text-xs font-semibold ${headerColor}`}>{headerText}</span>
        </div>
        {hasActions && (
          <div
            ref={menuRef}
            className="relative"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            role="presentation"
          >
            <button
              type="button"
              onClick={() => setMenuOpen((prev) => !prev)}
              className={`rounded p-1 hover:bg-black/5 ${headerColor}`}
            >
              <EllipsisVertical className="h-3.5 w-3.5" />
            </button>
            {menuOpen && (
              <AccountCardDropdown
                onDelete={() => {
                  setMenuOpen(false);
                  onDelete?.();
                }}
              />
            )}
          </div>
        )}
      </div>

      {status === 'syncing' && (
        <div className="flex flex-col items-center justify-center gap-3 px-4 py-10 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
          <p className="text-xs text-zinc-400">Sincronizando correos, un momento...</p>
        </div>
      )}

      {status === 'error' && (
        <div className="px-4 py-8 text-center">
          <p className="text-xs text-red-500">Error al sincronizar</p>
        </div>
      )}

      {status === 'ready' && emails.length === 0 && (
        <div className="px-4 py-8 text-center">
          <p className="text-xs text-zinc-400">Sin correos todavía</p>
        </div>
      )}

      {status === 'ready' && emails.length > 0 && (
        <div className="flex flex-col">
          {emails.map((emailItem, i) => (
            <div
              key={emailItem.provider_message_id}
              className={`flex flex-col gap-0.5 px-3.5 py-2.5 ${
                i > 0 ? 'border-t border-zinc-100' : ''
              } ${emailItem.is_read ? 'bg-white' : 'bg-zinc-50'}`}
            >
              <div className="flex items-center justify-between">
                <span
                  className={`text-xs ${
                    emailItem.is_read ? 'font-normal' : 'font-semibold'
                  } text-zinc-900`}
                >
                  {emailItem.from_name ?? emailItem.from_email}
                </span>
                <span className="text-[10px] text-zinc-400">
                  {formatShortDate(emailItem.received_at)}
                </span>
              </div>
              <span
                className={`text-[11px] ${
                  emailItem.is_read ? 'font-normal text-zinc-500' : 'font-medium text-zinc-600'
                }`}
              >
                {emailItem.subject ?? '(Sin asunto)'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
