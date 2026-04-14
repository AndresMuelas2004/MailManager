import { useState } from "react";
import { Send, X, ChevronDown } from "lucide-react";

type Account = {
  account_id: string;
  provider: string;
  email_address: string | null;
  display_label: string;
};

type UiError = { message: string };

type Props = {
  accounts: Account[];
  selectedAccountId: string;
  onSelectedAccountChange: (id: string) => void;
  to: string;
  onToChange: (v: string) => void;
  subject: string;
  onSubjectChange: (v: string) => void;
  body: string;
  onBodyChange: (v: string) => void;
  canSend: boolean;
  sending: boolean;
  error: UiError | null;
  onSend: () => void;
  onClose: () => void;
};

export default function ComposeOverlay({
  accounts,
  selectedAccountId,
  onSelectedAccountChange,
  to,
  onToChange,
  subject,
  onSubjectChange,
  body,
  onBodyChange,
  canSend,
  sending,
  error,
  onSend,
  onClose,
}: Props) {
  const [selectorOpen, setSelectorOpen] = useState(false);

  const selectedAccount = accounts.find((a) => a.account_id === selectedAccountId);
  const accountLabel = (a: Account) => a.email_address ?? a.display_label;

  return (
    <div className="absolute right-6 bottom-0 z-50 flex w-[400px] flex-col rounded-t-2xl border border-zinc-200 bg-white shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <h3 className="text-base font-semibold text-zinc-900">Nuevo mensaje</h3>
        <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-700">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex flex-col gap-4 px-5 pb-5">
        {/* Para */}
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-zinc-900">Para</label>
          <input
            type="text"
            value={to}
            onChange={(e) => onToChange(e.target.value)}
            placeholder="correo@ejemplo.com"
            className="h-10 rounded-[10px] border-[1.5px] border-zinc-200 px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
          />
        </div>

        {/* Origen */}
        <div className="relative flex flex-col gap-1.5">
          <label className="text-sm font-medium text-zinc-900">Origen</label>
          <button
            type="button"
            onClick={() => setSelectorOpen(!selectorOpen)}
            className="flex h-10 items-center justify-between rounded-[10px] bg-zinc-100 px-3 text-sm text-zinc-900"
          >
            <span>{selectedAccount ? accountLabel(selectedAccount) : "Selecciona una cuenta"}</span>
            <ChevronDown className="h-4 w-4 text-zinc-500" />
          </button>
          {selectorOpen && (
            <div className="absolute top-full left-0 z-10 mt-1 w-full rounded-[10px] border border-zinc-200 bg-white py-1 shadow-lg">
              {accounts.map((a) => (
                <button
                  key={a.account_id}
                  type="button"
                  onClick={() => { onSelectedAccountChange(a.account_id); setSelectorOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-50"
                >
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      a.provider === "gmail" ? "bg-red-500" : "bg-blue-600"
                    }`}
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

        {/* Asunto */}
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

        {/* Mensaje */}
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

        {/* Enviar */}
        <button
          type="button"
          disabled={!canSend}
          onClick={onSend}
          className="flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {sending ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
          ) : (
            <>
              <Send className="h-[18px] w-[18px]" />
              Enviar
            </>
          )}
        </button>
      </div>
    </div>
  );
}
