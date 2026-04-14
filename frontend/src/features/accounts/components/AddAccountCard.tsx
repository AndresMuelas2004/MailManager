import ProviderSelect from "./ProviderSelect";

type Props = {
  displayLabel: string;
  onDisplayLabelChange: (value: string) => void;
  selectedProvider: string;
  onProviderChange: (provider: string) => void;
  onAdd: () => void;
  canAdd: boolean;
  adding: boolean;
};

export default function AddAccountCard({
  displayLabel,
  onDisplayLabelChange,
  selectedProvider,
  onProviderChange,
  onAdd,
  canAdd,
  adding,
}: Props) {
  return (
    <div className="flex w-full flex-col items-center gap-4 rounded-2xl border-[1.5px] border-zinc-200 bg-white px-6 pb-4 pt-8">
      <h3 className="text-base font-semibold text-zinc-900">Añadir cuenta</h3>

      <div className="flex w-full flex-col gap-2">
        <label className="text-sm font-medium text-zinc-900">
          Nombre personalizado
        </label>
        <input
          type="text"
          value={displayLabel}
          onChange={(e) => onDisplayLabelChange(e.target.value)}
          placeholder="Ej: Cuenta principal (opcional)"
          maxLength={120}
          className="h-11 w-full rounded-[10px] border-[1.5px] border-zinc-200 bg-white px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
        />
      </div>

      <ProviderSelect value={selectedProvider} onChange={onProviderChange} />

      <button
        type="button"
        disabled={!canAdd}
        onClick={onAdd}
        className={`flex h-11 w-full items-center justify-center rounded-[10px] text-sm font-semibold transition-colors ${
          canAdd
            ? "bg-blue-600 text-white shadow-md shadow-blue-600/25 hover:bg-blue-700"
            : "cursor-not-allowed bg-gray-200 text-gray-400"
        }`}
      >
        {adding ? (
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
        ) : (
          "Añadir cuenta"
        )}
      </button>
    </div>
  );
}
