import { useState } from 'react';
import { LogOut, Trash2 } from 'lucide-react';

import ConfirmPopover from '../common/ConfirmPopover';

type Props = {
  onLogout: () => void;
  onDeleteAccount: () => void;
};

export default function SettingsDropdown({ onLogout, onDeleteAccount }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (confirmDelete) {
    return (
      <ConfirmPopover
        title="¿Estás seguro de que quieres eliminar tu cuenta?"
        description="Esta acción es irreversible y eliminará todos tus datos, buzones y cuentas conectadas."
        position="top"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={onDeleteAccount}
      />
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
