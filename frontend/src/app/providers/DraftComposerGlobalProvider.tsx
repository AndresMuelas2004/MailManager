import { useMemo, type ReactNode } from 'react';
import { matchPath, useLocation } from 'react-router-dom';

import useDraftComposer from './draftComposer/useDraftComposer';
import ComposeOverlay from '../../components/ui/ComposeOverlay';
import { DraftComposerContext, type DraftComposerContextValue } from './DraftComposerContext';

function useActiveMailboxId(): string | null {
  const { pathname } = useLocation();
  const match = matchPath('/m/:mailboxId/*', pathname);
  return match?.params.mailboxId ?? null;
}

type Props = {
  children: ReactNode;
};

export default function DraftComposerGlobalProvider({ children }: Props) {
  const mailboxId = useActiveMailboxId();
  const composer = useDraftComposer(mailboxId);

  const value = useMemo<DraftComposerContextValue>(
    () => ({
      openForNewEmail: composer.openForNewEmail,
      openForNewDraft: composer.openForNewDraft,
      openForEditDraft: composer.openForEditDraft,
      setRefreshCallback: composer.setRefreshCallback,
    }),
    [
      composer.openForNewEmail,
      composer.openForNewDraft,
      composer.openForEditDraft,
      composer.setRefreshCallback,
    ],
  );

  return (
    <DraftComposerContext.Provider value={value}>
      {children}
      {composer.open && composer.mode && (
        <ComposeOverlay
          mode={composer.mode}
          accounts={composer.accounts}
          selectedAccountId={composer.accountId}
          onSelectedAccountChange={composer.setAccountId}
          to={composer.to}
          onToChange={composer.setTo}
          cc={composer.cc}
          onCcChange={composer.setCc}
          bcc={composer.bcc}
          onBccChange={composer.setBcc}
          subject={composer.subject}
          onSubjectChange={composer.setSubject}
          body={composer.body}
          onBodyChange={composer.setBody}
          sending={composer.sending}
          saving={composer.saving}
          error={composer.error}
          canSendEmail={composer.canSendEmail}
          canSaveDraft={composer.canSaveDraft}
          canSendDraft={composer.canSendDraft}
          onSendEmail={composer.handleSendEmail}
          onSaveDraft={composer.handleSaveDraft}
          onSendDraft={composer.handleSendDraft}
          onClose={composer.closeWithX}
        />
      )}
    </DraftComposerContext.Provider>
  );
}
