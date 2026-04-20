import { useCallback } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '../providers/AuthContext';
import { useDraftComposerContext } from '../providers/DraftComposerContext';
import useCurrentUser from '../../lib/hooks/useCurrentUser';
import useMailboxList from '../../lib/hooks/useMailboxList';
import Sidebar from '../../components/ui/Sidebar';
import { MAILBOX_NAV_ITEMS } from './mailboxNavItems';

function MailboxShell({ mailboxId }: { mailboxId: string }) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { openForNewEmail } = useDraftComposerContext();

  const { mailboxes, currentMailboxName, handleCreate } = useMailboxList(mailboxId);
  const { deleteCurrentUser } = useCurrentUser();

  const handleLogout = useCallback(async () => {
    await logout();
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  const handleDeleteAccount = useCallback(async () => {
    await deleteCurrentUser();
    await logout();
    navigate('/login', { replace: true });
  }, [deleteCurrentUser, logout, navigate]);

  const handleMailboxSelect = useCallback(
    (id: string) => navigate(`/m/${id}/accounts`),
    [navigate],
  );

  const handleMailboxCreate = useCallback(
    async (displayName: string) => {
      const created = await handleCreate(displayName);
      if (created) navigate(`/m/${created.mailbox_id}/accounts`);
    },
    [handleCreate, navigate],
  );

  return (
    <div className="flex min-h-screen bg-[#F9FAFB]">
      <Sidebar
        mailboxId={mailboxId}
        mailboxName={currentMailboxName}
        mailboxes={mailboxes}
        navItems={MAILBOX_NAV_ITEMS}
        onMailboxSelect={handleMailboxSelect}
        onMailboxCreate={handleMailboxCreate}
        onCompose={openForNewEmail}
        onLogout={handleLogout}
        onDeleteAccount={handleDeleteAccount}
      />
      <div className="relative flex-1">
        <Outlet />
      </div>
    </div>
  );
}

export default function MailboxLayout() {
  const { mailboxId } = useParams<{ mailboxId: string }>();
  if (!mailboxId) return null;

  return <MailboxShell mailboxId={mailboxId} />;
}
