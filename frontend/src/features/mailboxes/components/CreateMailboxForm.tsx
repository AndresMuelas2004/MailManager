import { Lightbulb } from 'lucide-react';
import type { UiError } from '../../../api/client/errors';

type Props = {
  displayName: string;
  onDisplayNameChange: (value: string) => void;
  onSubmit: () => void;
  canSubmit: boolean;
  loading: boolean;
  error: UiError | null;
};

export default function CreateMailboxForm({
  displayName,
  onDisplayNameChange,
  onSubmit,
  canSubmit,
  loading,
  error,
}: Props) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-[#F8FAFC] px-20">
      <div className="flex w-full max-w-[420px] flex-col gap-8">
        <span className="w-fit rounded-full bg-blue-50 px-4 py-1.5 text-[13px] font-medium text-blue-600">
          Paso 1 — Configuración inicial
        </span>

        <div className="flex flex-col gap-2.5">
          <h2 className="text-[32px] font-bold tracking-tight text-slate-950">
            Crea tu primera bandeja
          </h2>
          <p className="text-base leading-[1.5] text-slate-500">
            Dale un nombre a tu bandeja de correo unificada. Podrás cambiarlo más tarde.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="mailbox-name" className="text-sm font-medium text-zinc-900">
            Nombre de la bandeja
          </label>
          <input
            id="mailbox-name"
            type="text"
            value={displayName}
            onChange={(e) => onDisplayNameChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canSubmit) onSubmit();
            }}
            placeholder="Ej: Trabajo, Personal, Universidad..."
            maxLength={120}
            className="h-12 w-full rounded-xl border-[1.5px] border-zinc-200 bg-white px-4 text-[15px] text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
          />
        </div>

        <button
          type="button"
          disabled={!canSubmit}
          onClick={onSubmit}
          className={`flex h-[52px] w-full items-center justify-center rounded-xl text-base font-semibold transition-colors ${
            canSubmit
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25 hover:bg-blue-700'
              : 'cursor-not-allowed bg-gray-200 text-gray-400'
          }`}
        >
          {loading ? (
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
          ) : (
            'Crear bandeja'
          )}
        </button>

        {error && <p className="text-center text-sm text-red-600">{error.message}</p>}

        <div className="flex items-center justify-center gap-2">
          <Lightbulb className="h-4 w-4 text-slate-400" />
          <span className="text-[13px] text-slate-400">Puedes crear más bandejas después</span>
        </div>
      </div>
    </div>
  );
}
