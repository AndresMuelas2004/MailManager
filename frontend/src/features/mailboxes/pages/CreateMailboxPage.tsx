import { CheckCircle } from "lucide-react";

import useCreateMailbox from "../hooks/useCreateMailbox";
import CreateMailboxBranding from "../components/CreateMailboxBranding";
import CreateMailboxForm from "../components/CreateMailboxForm";

export default function CreateMailboxPage() {
  const {
    displayName,
    setDisplayName,
    canSubmit,
    loading,
    error,
    createdMailbox,
    handleCreate,
  } = useCreateMailbox();

  return (
    <div className="flex min-h-screen">
      <CreateMailboxBranding />

      {createdMailbox ? (
        <div className="flex flex-1 flex-col items-center justify-center bg-[#F8FAFC] px-20">
          <div className="flex max-w-[420px] flex-col items-center gap-6 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
              <CheckCircle className="h-8 w-8 text-green-600" />
            </div>
            <h2 className="text-[28px] font-bold tracking-tight text-slate-950">
              Bandeja &ldquo;{createdMailbox.display_name}&rdquo; creada
            </h2>
            <p className="text-base leading-[1.5] text-slate-500">
              Pronto podrás gestionar tu correo aquí.
              Las siguientes pantallas están en camino.
            </p>
          </div>
        </div>
      ) : (
        <CreateMailboxForm
          displayName={displayName}
          onDisplayNameChange={setDisplayName}
          onSubmit={handleCreate}
          canSubmit={canSubmit}
          loading={loading}
          error={error}
        />
      )}
    </div>
  );
}
