import { useState } from "react";
import { Inbox, Plus, Check } from "lucide-react";

type MailboxItem = {
  mailbox_id: string;
  display_name: string | null;
};

type Props = {
  mailboxes: MailboxItem[];
  currentMailboxId: string;
  onSelect: (mailboxId: string) => void;
  onCreate: (displayName: string) => void;
};

export default function MailboxDropdown({ mailboxes, currentMailboxId, onSelect, onCreate }: Props) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  function handleCreate() {
    const trimmed = newName.trim();
    if (trimmed.length === 0) return;
    onCreate(trimmed);
    setNewName("");
    setCreating(false);
  }

  return (
    <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-xl border border-zinc-200 bg-white py-1 shadow-lg">
      {mailboxes.map((m) => (
        <button
          key={m.mailbox_id}
          type="button"
          onClick={() => onSelect(m.mailbox_id)}
          className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm hover:bg-zinc-50"
        >
          <Inbox className="h-4 w-4 text-blue-600" />
          <span className="flex-1 text-zinc-900">{m.display_name}</span>
          {m.mailbox_id === currentMailboxId && (
            <Check className="h-4 w-4 text-blue-600" />
          )}
        </button>
      ))}

      <div className="mx-2 my-1 h-px bg-zinc-100" />

      {creating ? (
        <div className="flex items-center gap-2 px-3 py-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
            placeholder="Nombre de la bandeja"
            autoFocus
            className="h-8 flex-1 rounded-lg border border-zinc-200 px-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-600 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleCreate}
            disabled={newName.trim().length === 0}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white disabled:opacity-40"
          >
            <Check className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-blue-600 hover:bg-zinc-50"
        >
          <Plus className="h-4 w-4" />
          Crear nueva bandeja
        </button>
      )}
    </div>
  );
}
