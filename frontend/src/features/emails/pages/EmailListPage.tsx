import { useParams } from "react-router-dom";
import { Send, Inbox, ShieldAlert, FileEdit, Trash2 } from "lucide-react";

import useEmailList from "../hooks/useEmailList";
import useAccountInbox from "../hooks/useAccountInbox";
import type { AccountTab } from "../hooks/useAccountInbox";
import EmailTable from "../components/EmailTable";
import DraftsTable from "../../drafts/components/DraftsTable";
import type { EmailBox } from "../../../lib/types";

type Props = {
  box: EmailBox;
};

const PAGE_CONFIG: Record<string, { title: string; subtitle: string }> = {
  ALL_MAIL: {
    title: "Bandeja unificada",
    subtitle: "Todos los correos de tus cuentas conectadas en un solo lugar.",
  },
  SENT: {
    title: "Correos enviados",
    subtitle: "Todos los correos enviados desde tus cuentas conectadas.",
  },
  SPAM: {
    title: "Bandeja de spam",
    subtitle: "Correos no deseados de tus cuentas conectadas.",
  },
  TRASH: {
    title: "Papelera de reciclaje",
    subtitle: "Correos eliminados de tus cuentas conectadas.",
  },
};

const ACCOUNT_TABS: { key: AccountTab; label: string; icon: typeof Inbox }[] = [
  { key: "ALL_MAIL", label: "Bandeja", icon: Inbox },
  { key: "SENT", label: "Enviados", icon: Send },
  { key: "SPAM", label: "Spam", icon: ShieldAlert },
  { key: "DRAFTS", label: "Borradores", icon: FileEdit },
  { key: "TRASH", label: "Papelera", icon: Trash2 },
];

function isGenericLabel(label: string, provider: string): boolean {
  const generic = provider === "gmail" ? "Gmail" : "Outlook";
  return label === generic || label.toLowerCase() === provider.toLowerCase();
}

function AccountInboxView({ mailboxId, accountId }: { mailboxId: string; accountId: string }) {
  const {
    emails, drafts, accounts, activeTab, setActiveTab, isDraftsTab, loading, error,
  } = useAccountInbox(mailboxId, accountId);

  const account = accounts.find((a) => a.account_id === accountId);
  const hasCustomLabel = account ? !isGenericLabel(account.display_label, account.provider) : false;
  const email = account?.email_address ?? account?.display_label ?? accountId;
  const title = hasCustomLabel && account
    ? `${account.display_label} - ${email}`
    : email;

  const bandejaLabel = hasCustomLabel && account
    ? `Bandeja ${account.display_label}`
    : `Bandeja ${email}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-2">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">{title}</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">Correos de {title}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-zinc-200 px-8">
        {ACCOUNT_TABS.map(({ key, label, icon: Icon }) => {
          const isActive = activeTab === key;
          const tabLabel = key === "ALL_MAIL" ? bandejaLabel : label;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-zinc-500 hover:text-zinc-700"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tabLabel}
            </button>
          );
        })}
      </div>

      {error ? (
        <div className="px-8 pt-4 text-sm text-red-600">{error.message}</div>
      ) : isDraftsTab ? (
        <DraftsTable drafts={drafts} accounts={accounts} loading={loading} />
      ) : (
        <EmailTable emails={emails} accounts={accounts} loading={loading} />
      )}
    </div>
  );
}

function UnifiedView({ mailboxId, box }: { mailboxId: string; box: EmailBox }) {
  const { emails, accounts, loading, error } = useEmailList(mailboxId, box);
  const config = PAGE_CONFIG[box] ?? PAGE_CONFIG.ALL_MAIL;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-6">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">{config.title}</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">{config.subtitle}</p>
      </div>
      {error ? (
        <div className="px-8 text-sm text-red-600">{error.message}</div>
      ) : (
        <EmailTable emails={emails} accounts={accounts} loading={loading} />
      )}
    </div>
  );
}

export default function EmailListPage({ box }: Props) {
  const { mailboxId, accountId } = useParams<{ mailboxId: string; accountId: string }>();

  if (accountId) {
    return <AccountInboxView mailboxId={mailboxId!} accountId={accountId} />;
  }

  return <UnifiedView mailboxId={mailboxId!} box={box} />;
}
