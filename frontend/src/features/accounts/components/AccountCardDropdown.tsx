import { useState } from 'react';
import { Trash2 } from 'lucide-react';

import ConfirmModal from '../../../components/common/ConfirmModal';

type Props = {
  onDelete: () => void;
};

export default function AccountCardDropdown({ onDelete }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <>
      <div className="absolute right-0 top-full z-30 mt-1 w-56 rounded-xl border border-zinc-200 bg-white py-1 shadow-lg">
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-red-600 hover:bg-red-50"
        >
          <Trash2 className="h-4 w-4" />
          Eliminar cuenta
        </button>
      </div>
      {confirmDelete && (
        <ConfirmModal
          title="¿Eliminar esta cuenta?"
          description="Se eliminarán los correos y borradores asociados a esta cuenta."
          onCancel={() => setConfirmDelete(false)}
          onConfirm={onDelete}
        />
      )}
    </>
  );
}
