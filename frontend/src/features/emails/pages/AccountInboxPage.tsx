import { useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

import useEmailList from '../hooks/useEmailList';
import useEmailViewer from '../hooks/useEmailViewer';
import useBulkBar from '../hooks/useBulkBar';
import EmailTable from '../components/EmailTable';
import ViewerMount from '../components/ViewerMount';
import AccountTabs from '../components/AccountTabs';
import SearchInput from '../components/SearchInput';
import useDebounce from '../hooks/useDebounce';
import { isGenericLabel } from '../../../lib/providers';
import type { EmailBox } from '../../../lib/types';

type Props = {
  box: EmailBox;
};

const SEARCH_DEBOUNCE_MS = 300;
const MIN_SEARCH_LENGTH = 2;

export default function AccountInboxPage({ box }: Props) {
  const { mailboxId, accountId } = useParams<{
    mailboxId: string;
    accountId: string;
  }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawQ = searchParams.get('q') ?? '';
  const debouncedQ = useDebounce(rawQ, SEARCH_DEBOUNCE_MS);

  const { emails, accounts, loading, error, refresh } = useEmailList(
    mailboxId!,
    box,
    accountId!,
    debouncedQ,
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
    const computedTitle = hasCustomLabel && account ? `${account.display_label} - ${email}` : email;
    const computedBandeja =
      hasCustomLabel && account ? `Bandeja ${account.display_label}` : `Bandeja ${email}`;
    return { title: computedTitle, bandejaLabel: computedBandeja };
  }, [accounts, accountId]);

  const combinedError = error || bulkError;
  const basePath = `/m/${mailboxId}/account/${accountId}`;

  const handleSearchChange = (next: string) => {
    const params = new URLSearchParams(searchParams);
    if (next.length === 0) params.delete('q');
    else params.set('q', next);
    setSearchParams(params, { replace: true });
  };

  const isSearching = debouncedQ.trim().length >= MIN_SEARCH_LENGTH;
  const emptyMessage = isSearching
    ? 'No se encontraron correos para tu búsqueda.'
    : 'No hay correos en esta bandeja';

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2 px-8 pt-8 pb-2">
        <h1 className="text-[28px] font-bold tracking-tight text-zinc-900">{title}</h1>
        <p className="text-[15px] leading-[1.5] text-zinc-500">Correos de {title}</p>
      </div>

      <AccountTabs basePath={basePath} inboxLabel={bandejaLabel} />

      <div className="px-8 pt-4">
        <SearchInput value={rawQ} onChange={handleSearchChange} />
      </div>

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
        emptyMessage={emptyMessage}
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
