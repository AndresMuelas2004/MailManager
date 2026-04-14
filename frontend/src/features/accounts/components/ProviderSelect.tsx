import { useState } from "react";
import { ChevronDown, Mail } from "lucide-react";

type Props = {
  value: string;
  onChange: (provider: string) => void;
};

const providers = [
  { id: "gmail", label: "Gmail", color: "text-red-600" },
  { id: "outlook", label: "Outlook", color: "text-blue-600" },
];

export default function ProviderSelect({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const selected = providers.find((p) => p.id === value);

  return (
    <div className="relative flex flex-col gap-2">
      <label className="text-sm font-medium text-zinc-900">Proveedor</label>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-11 items-center justify-between rounded-[10px] border-[1.5px] border-zinc-200 bg-white px-3 text-sm"
      >
        {selected ? (
          <span className="flex items-center gap-2">
            <Mail className={`h-4 w-4 ${selected.color}`} />
            <span className="text-zinc-900">{selected.label}</span>
          </span>
        ) : (
          <span className="text-zinc-400">Selecciona un proveedor...</span>
        )}
        <ChevronDown className="h-4 w-4 text-zinc-500" />
      </button>

      {open && (
        <div className="absolute top-full left-0 z-10 mt-1 w-full rounded-[10px] border border-zinc-200 bg-white py-1 shadow-lg">
          {providers.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => { onChange(p.id); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-zinc-50"
            >
              <Mail className={`h-4 w-4 ${p.color}`} />
              <span className="text-zinc-900">{p.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
