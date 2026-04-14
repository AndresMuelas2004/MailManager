import { useNavigate, useParams } from "react-router-dom";

import useConnectedAccounts from "../hooks/useConnectedAccounts";
import AddAccountCard from "../components/AddAccountCard";
import AccountCard from "../components/AccountCard";
import Spinner from "../../../components/common/Spinner";

export default function ConnectedAccountsPage() {
  const { mailboxId } = useParams<{ mailboxId: string }>();
  const navigate = useNavigate();

  const {
    entries,
    loading,
    displayLabel,
    setDisplayLabel,
    selectedProvider,
    setSelectedProvider,
    canAdd,
    addingAccount,
    addAccount,
    removeAccount,
    error,
  } = useConnectedAccounts(mailboxId!);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8 px-8 pt-8 pb-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">
          Cuentas conectadas
        </h1>
        <p className="max-w-[600px] text-[15px] leading-[1.5] text-zinc-500">
          Gestiona las cuentas de correo vinculadas a tu bandeja unificada.
        </p>
      </div>

      <div className="flex gap-4">
        <div className="w-full max-w-[240px]">
          <AddAccountCard
            displayLabel={displayLabel}
            onDisplayLabelChange={setDisplayLabel}
            selectedProvider={selectedProvider}
            onProviderChange={setSelectedProvider}
            onAdd={addAccount}
            canAdd={canAdd}
            adding={addingAccount}
          />
        </div>

        {entries.map((entry) => (
          <div key={entry.account.account_id} className="w-full max-w-[280px]">
            <AccountCard
              account={entry.account}
              emails={entry.emails}
              status={entry.status}
              onClick={() =>
                navigate(`/m/${mailboxId}/account/${entry.account.account_id}`)
              }
              onDelete={() => removeAccount(entry.account.account_id)}
            />
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">{error.message}</p>}
    </div>
  );
}
