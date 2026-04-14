import { X, Flame } from "lucide-react";

type Props = {
  selectedCount: number;
  disabled: boolean;
  onClear: () => void;
  onDelete: () => void;
};

export default function DraftBulkActionsBar({
  selectedCount,
  disabled,
  onClear,
  onDelete,
}: Props) {
  return (
    <div className="flex w-full items-center gap-2">
      <button
        type="button"
        onClick={onClear}
        className="flex h-7 w-7 items-center justify-center rounded hover:bg-zinc-100"
        aria-label="Limpiar selección"
      >
        <X className="h-[18px] w-[18px] text-zinc-600" />
      </button>
      <span className="text-[13px] font-medium text-zinc-700">
        {selectedCount} seleccionado{selectedCount === 1 ? "" : "s"}
      </span>
      <div className="mx-2 h-5 w-px bg-zinc-200" />
      <button
        type="button"
        onClick={onDelete}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded px-2.5 py-1 text-[13px] font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50"
      >
        <Flame className="h-[18px] w-[18px]" />
        Eliminar
      </button>
    </div>
  );
}
