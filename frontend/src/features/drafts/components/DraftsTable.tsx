import { RefreshCw } from "lucide-react";

import { formatShortDate, resolveAccount } from "../../../lib/formatters";
import Spinner from "../../../components/common/Spinner";
import type { DraftOut, AccountOut } from "../../../api/types/dto";

type Props = {
  drafts: DraftOut[];
  accounts: AccountOut[];
  loading: boolean;
};

export default function DraftsTable({ drafts, accounts, loading }: Props) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* Toolbar */}
      <div className="flex h-11 items-center gap-4 border-b border-zinc-200 px-8">
        <div className="h-[18px] w-[18px] rounded border-[1.5px] border-zinc-300" />
        <RefreshCw className="h-[18px] w-[18px] text-zinc-500" />
        <span className="text-[13px] font-medium text-zinc-500">
          {drafts.length} borradores
        </span>
      </div>

      {/* Column headers */}
      <div className="flex h-8 items-center gap-3 border-b border-zinc-200 px-8 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
        <div className="w-[18px]" />
        <div className="w-[120px]">Remitente</div>
        <div className="w-[170px]">Para</div>
        <div className="w-[170px]">De</div>
        <div className="flex-1">Asunto</div>
        <div className="w-16 text-right">Fecha</div>
      </div>

      {/* Rows */}
      {drafts.length === 0 ? (
        <div className="py-16 text-center text-sm text-zinc-400">
          No hay borradores guardados
        </div>
      ) : (
        drafts.map((draft) => {
          const { providerName, accountEmail } = resolveAccount(draft.account_id, accounts);
          const toDisplay = draft.to_recipients.length > 0
            ? draft.to_recipients[0]
            : "(Sin destinatario)";

          return (
            <div
              key={`${draft.provider_draft_id}-${draft.account_id}`}
              className="flex h-11 items-center gap-3 border-b border-zinc-100 bg-white px-8"
            >
              <div className="h-[18px] w-[18px] rounded border-[1.5px] border-zinc-300" />
              <div className="w-[120px] truncate text-[13px] text-zinc-900">
                {providerName}
              </div>
              <div className="w-[170px] truncate text-xs text-zinc-900">
                {toDisplay}
              </div>
              <div className="w-[170px] truncate text-xs text-zinc-900">
                {accountEmail}
              </div>
              <div className="flex-1 truncate text-[13px] text-zinc-900">
                {draft.subject || "(Sin asunto)"}
              </div>
              <div className="w-16 text-right text-xs text-zinc-900">
                {formatShortDate(draft.created_at)}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
