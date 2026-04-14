import { useMemo } from "react";
import { useParams } from "react-router-dom";

import useEmailList from "../hooks/useEmailList";
import useEmailViewer from "../hooks/useEmailViewer";
import useBulkBar from "../hooks/useBulkBar";
import EmailTable from "../components/EmailTable";
import ViewerMount from "../components/ViewerMount";
import AccountTabs from "../components/AccountTabs";
import { isGenericLabel } from "../../../lib/providers";
import type { EmailBox } from "../../../lib/types";

type Props = {
  box: EmailBox;
};

export default function AccountInboxPage({ box }: Props) {
  const { mailboxId, accountId } = useParams<{
    mailboxId: string;
    accountId: string;
  }>();
  const { emails, accounts, loading, error, refresh } = useEmailList(
    mailboxId!,
    box,
    accountId!,
  );

  const { selection, bulkError, bulkBar } = useBulkBar({
    mailboxId: mailboxId!,
    box,
    emails,
    refresh,
  });

  const viewer = useEmailViewer(mailboxId!, refresh);

  const { title, bandejaLabel } = useMemo(() => {
    const account = accounts.find((a) => a.account_id === accountId);
    const hasCustomLabel = account
      ? !isGenericLabel(account.display_label, account.provider)
      : false;
    const email = account?.email_address ?? account?.display_label ?? accountId!;
    const computedTitle =
      hasCustomLabel && account ? `${account.display_label} - ${email}` : email;
    const computedBandeja =
      hasCustomLabel && account ? `Bandeja ${account.display_label}` : `Bandeja ${email}`;
    return { title: computedTitle, bandejaLabel: computedBandeja };
  }, [accounts, accountId]);

  const combinedError = error || bulkError;
  const basePath = `/m/${mailboxId}/account/${accountId}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-2">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">{title}</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">Correos de {title}</p>
      </div>

      <AccountTabs basePath={basePath} inboxLabel={bandejaLabel} />

      {combinedError && (
        <div className="px-8 pt-4 text-sm text-red-600">{combinedError.message}</div>
      )}

      <EmailTable
        emails={emails}
        accounts={accounts}
        loading={loading}
        hasSelection={selection.size > 0}
        isSelected={selection.isSelected}
        onToggle={selection.toggle}
        onToggleAll={() => selection.toggleTopN(emails)}
        onOpen={viewer.open}
        headerCheckboxState={selection.headerState(emails)}
        bulkBar={bulkBar}
      />

      <ViewerMount
        mailboxId={mailboxId!}
        openedEmail={viewer.openedEmail}
        accounts={accounts}
        onClose={viewer.close}
        onRead={viewer.handleRead}
      />
    </div>
  );
}
