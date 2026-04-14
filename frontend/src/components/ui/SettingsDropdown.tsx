import { useState } from "react";
import { LogOut, Trash2 } from "lucide-react";

type Props = {
  onLogout: () => void;
  onDeleteAccount: () => void;
};

export default function SettingsDropdown({ onLogout, onDeleteAccount }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (confirmDelete) {
    return (
      <div className="absolute bottom-full left-0 z-30 mb-2 w-72 rounded-xl border border-zinc-200 bg-white p-5 shadow-lg">
        <p className="text-sm font-semibold text-zinc-900">
          ¿Estás seguro de que quieres eliminar tu cuenta?
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">
          Esta acción es irreversible y eliminará todos tus datos, buzones y cuentas conectadas.
        </p>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => setConfirmDelete(false)}
            className="flex-1 rounded-lg border border-zinc-200 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onDeleteAccount}
            className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Eliminar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute bottom-full left-0 z-30 mb-2 w-56 rounded-xl border border-zinc-200 bg-white py-1 shadow-lg">
      <button
        type="button"
        onClick={onLogout}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-zinc-700 hover:bg-zinc-50"
      >
        <LogOut className="h-4 w-4" />
        Cerrar sesión
      </button>
      <button
        type="button"
        onClick={() => setConfirmDelete(true)}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-red-600 hover:bg-red-50"
      >
        <Trash2 className="h-4 w-4" />
        Eliminar cuenta
      </button>
    </div>
  );
}
