import { useParams } from "react-router-dom";

import useEmailList from "../hooks/useEmailList";
import useEmailViewer from "../hooks/useEmailViewer";
import useBulkBar from "../hooks/useBulkBar";
import EmailTable from "../components/EmailTable";
import ViewerMount from "../components/ViewerMount";
import { EMAIL_BOX_CONFIG } from "../boxes";
import type { EmailBox } from "../../../lib/types";

type Props = {
  box: EmailBox;
};

export default function UnifiedInboxPage({ box }: Props) {
  const { mailboxId } = useParams<{ mailboxId: string }>();
  const { emails, accounts, loading, error, refresh } = useEmailList(mailboxId!, box);
  const config = EMAIL_BOX_CONFIG[box];

  const { selection, bulkError, bulkBar } = useBulkBar({
    mailboxId: mailboxId!,
    box,
    emails,
    refresh,
  });

  const viewer = useEmailViewer(mailboxId!, refresh);

  const combinedError = error || bulkError;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-6">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">{config.title}</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">{config.subtitle}</p>
      </div>
      {combinedError ? (
        <div className="px-8 text-sm text-red-600">{combinedError.message}</div>
      ) : (
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
      )}
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
