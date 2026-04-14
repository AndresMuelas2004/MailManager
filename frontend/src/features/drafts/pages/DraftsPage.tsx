import { useParams } from "react-router-dom";

import useDraftsList from "../hooks/useDraftsList";
import DraftsTable from "../components/DraftsTable";

export default function DraftsPage() {
  const { mailboxId } = useParams<{ mailboxId: string }>();
  const { drafts, accounts, loading, error } = useDraftsList(mailboxId!);

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-6">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">Borradores</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">
          Borradores guardados de tus cuentas conectadas.
        </p>
      </div>

      {error ? (
        <div className="px-8 text-sm text-red-600">{error.message}</div>
      ) : (
        <DraftsTable drafts={drafts} accounts={accounts} loading={loading} />
      )}
    </div>
  );
}
