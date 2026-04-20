import { useState } from 'react';
import { Send, X, ChevronDown, Save } from 'lucide-react';

import Spinner from '../common/Spinner';
import { getProviderMeta } from '../../lib/providers';
import type { ComposerMode } from '../../lib/types';
import type { UiError } from '../../api/client/errors';
import type { AccountOut } from '../../api/types/dto';

type ComposeAccount = Pick<
  AccountOut,
  'account_id' | 'provider' | 'email_address' | 'display_label'
>;

type Props = {
  mode: ComposerMode;
  accounts: ComposeAccount[];
  selectedAccountId: string;
  onSelectedAccountChange: (id: string) => void;
  to: string;
  onToChange: (v: string) => void;
  cc: string;
  onCcChange: (v: string) => void;
  bcc: string;
  onBccChange: (v: string) => void;
  subject: string;
  onSubjectChange: (v: string) => void;
  body: string;
  onBodyChange: (v: string) => void;
  sending: boolean;
  saving: boolean;
  error: UiError | null;
  canSendEmail: boolean;
  canSaveDraft: boolean;
  canSendDraft: boolean;
  onSendEmail: () => void;
  onSaveDraft: () => void;
  onSendDraft: () => void;
  onClose: () => void;
};

const TITLE_BY_MODE: Record<ComposerMode, string> = {
  new_email: 'Nuevo mensaje',
  new_draft: 'Nuevo borrador',
  edit_draft: 'Editar borrador',
};

export default function ComposeOverlay({
  mode,
  accounts,
  selectedAccountId,
  onSelectedAccountChange,
  to,
  onToChange,
  cc,
  onCcChange,
  bcc,
  onBccChange,
  subject,
  onSubjectChange,
  body,
  onBodyChange,
  sending,
  saving,
  error,
  canSendEmail,
  canSaveDraft,
  canSendDraft,
  onSendEmail,
  onSaveDraft,
  onSendDraft,
  onClose,
}: Props) {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [ccBccOpen, setCcBccOpen] = useState(() => cc.trim().length > 0 || bcc.trim().length > 0);

  const selectedAccount = accounts.find((a) => a.account_id === selectedAccountId);
  const accountLabel = (a: ComposeAccount) => a.email_address ?? a.display_label;
  const title = TITLE_BY_MODE[mode];

  const showSendEmail = mode === 'new_email';
  const showSaveDraft = mode === 'new_draft' || mode === 'edit_draft';
  const showSendDraft = mode === 'edit_draft';

  return (
    <div className="fixed right-6 bottom-0 z-50 flex w-[400px] flex-col rounded-t-2xl border border-zinc-200 bg-white shadow-xl">
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <h3 className="text-base font-semibold text-zinc-900">{title}</h3>
        <button
          type="button"
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-700"
          aria-label="Cerrar"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex flex-col gap-4 px-5 pb-5">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-zinc-900">Para</label>
            {!ccBccOpen && (
              <button
                type="button"
                onClick={() => setCcBccOpen(true)}
                className="text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                Añadir CC/BCC
              </button>
            )}
          </div>
          <input
            type="text"
            value={to}
            onChange={(e) => onToChange(e.target.value)}
            placeholder="correo@ejemplo.com"
            className="h-10 rounded-[10px] border-[1.5px] border-zinc-200 px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
          />
        </div>

        {ccBccOpen && (
          <>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-zinc-900">CC</label>
              <input
                type="text"
                value={cc}
                onChange={(e) => onCcChange(e.target.value)}
                placeholder="cc@ejemplo.com"
                className="h-10 rounded-[10px] border-[1.5px] border-zinc-200 px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-zinc-900">BCC</label>
              <input
                type="text"
                value={bcc}
                onChange={(e) => onBccChange(e.target.value)}
                placeholder="bcc@ejemplo.com"
                className="h-10 rounded-[10px] border-[1.5px] border-zinc-200 px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
              />
            </div>
          </>
        )}

        <div className="relative flex flex-col gap-1.5">
          <label className="text-sm font-medium text-zinc-900">Origen</label>
          <button
            type="button"
            onClick={() => setSelectorOpen((v) => !v)}
            disabled={mode === 'edit_draft'}
            className="flex h-10 items-center justify-between rounded-[10px] bg-zinc-100 px-3 text-sm text-zinc-900 disabled:opacity-70"
          >
            <span>{selectedAccount ? accountLabel(selectedAccount) : 'Selecciona una cuenta'}</span>
            {mode !== 'edit_draft' && <ChevronDown className="h-4 w-4 text-zinc-500" />}
          </button>
          {selectorOpen && mode !== 'edit_draft' && (
            <div className="absolute top-full left-0 z-10 mt-1 w-full rounded-[10px] border border-zinc-200 bg-white py-1 shadow-lg">
              {accounts.map((a) => (
                <button
                  key={a.account_id}
                  type="button"
                  onClick={() => {
                    onSelectedAccountChange(a.account_id);
                    setSelectorOpen(false);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-50"
                >
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${getProviderMeta(a.provider).dotClass}`}
                  />
                  <span className="flex-1 text-zinc-900">{accountLabel(a)}</span>
                  {a.account_id === selectedAccountId && (
                    <span className="text-xs text-blue-600">&#10003;</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-zinc-900">Asunto</label>
          <input
            type="text"
            value={subject}
            onChange={(e) => onSubjectChange(e.target.value)}
            placeholder="Escribe el asunto..."
            className="h-10 rounded-[10px] border-[1.5px] border-zinc-200 px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
          />
        </div>

        <div className="flex flex-1 flex-col gap-1.5">
          <label className="text-sm font-medium text-zinc-900">Mensaje</label>
          <textarea
            value={body}
            onChange={(e) => onBodyChange(e.target.value)}
            placeholder="Escribe tu mensaje..."
            rows={6}
            className="resize-none rounded-[10px] border-[1.5px] border-zinc-200 p-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
          />
        </div>

        {error && <p className="text-center text-sm text-red-600">{error.message}</p>}

        <div className="flex flex-col gap-2">
          {showSendEmail && (
            <button
              type="button"
              disabled={!canSendEmail}
              onClick={onSendEmail}
              className="flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {sending ? (
                <Spinner size="sm" color="white" />
              ) : (
                <>
                  <Send className="h-[18px] w-[18px]" />
                  Enviar
                </>
              )}
            </button>
          )}

          {showSendDraft && (
            <button
              type="button"
              disabled={!canSendDraft}
              onClick={onSendDraft}
              className="flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {sending ? (
                <Spinner size="sm" color="white" />
              ) : (
                <>
                  <Send className="h-[18px] w-[18px]" />
                  Enviar borrador
                </>
              )}
            </button>
          )}

          {showSaveDraft && (
            <button
              type="button"
              disabled={!canSaveDraft}
              onClick={onSaveDraft}
              className="flex h-11 items-center justify-center gap-2 rounded-xl border-[1.5px] border-zinc-200 bg-white text-sm font-semibold text-zinc-900 transition-colors hover:bg-zinc-50 disabled:opacity-50"
            >
              {saving ? (
                <Spinner size="sm" />
              ) : (
                <>
                  <Save className="h-[18px] w-[18px]" />
                  Guardar
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
