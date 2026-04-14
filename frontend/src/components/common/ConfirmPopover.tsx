type Position = "top" | "bottom";

type Props = {
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  position?: Position;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function ConfirmPopover({
  title,
  description,
  confirmLabel = "Eliminar",
  cancelLabel = "Cancelar",
  position = "bottom",
  onCancel,
  onConfirm,
}: Props) {
  const anchor =
    position === "top"
      ? "bottom-full left-0 mb-2"
      : "right-0 top-full mt-1";
  return (
    <div
      className={`absolute ${anchor} z-30 w-72 rounded-xl border border-zinc-200 bg-white p-5 shadow-lg`}
    >
      <p className="text-sm font-semibold text-zinc-900">{title}</p>
      <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">{description}</p>
      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-lg border border-zinc-200 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-medium text-white hover:bg-red-700"
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}
