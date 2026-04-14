import { useCallback, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../providers/AuthContext";
import { deleteAccount } from "../../api/endpoints/auth";
import useMailboxList from "../../features/mailboxes/hooks/useMailboxList";
import useComposeEmail from "../../features/emails/hooks/useComposeEmail";
import Sidebar from "../../components/ui/Sidebar";
import ComposeOverlay from "../../components/ui/ComposeOverlay";

export default function MailboxLayout() {
  const { mailboxId } = useParams<{ mailboxId: string }>();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [composeOpen, setComposeOpen] = useState(false);

  const { mailboxes, currentMailboxName, handleCreate } = useMailboxList(mailboxId!);

  const handleLogout = useCallback(async () => {
    await logout();
    navigate("/login", { replace: true });
  }, [logout, navigate]);

  const handleDeleteAccount = useCallback(async () => {
    try {
      await deleteAccount();
      await logout();
    } catch { /* logout anyway */ }
    navigate("/login", { replace: true });
  }, [logout, navigate]);

  const closeCompose = useCallback(() => setComposeOpen(false), []);
  const compose = useComposeEmail(mailboxId!, closeCompose);

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

  if (!mailboxId) return null;

  return (
    <div className="flex min-h-screen bg-[#F9FAFB]">
      <Sidebar
        mailboxId={mailboxId}
        mailboxName={currentMailboxName}
        mailboxes={mailboxes}
        onMailboxSelect={handleMailboxSelect}
        onMailboxCreate={handleMailboxCreate}
        onCompose={() => setComposeOpen(true)}
        onLogout={handleLogout}
        onDeleteAccount={handleDeleteAccount}
      />
      <div className="relative flex-1">
        <Outlet />
        {composeOpen && (
          <ComposeOverlay
            accounts={compose.accounts}
            selectedAccountId={compose.selectedAccountId}
            onSelectedAccountChange={compose.setSelectedAccountId}
            to={compose.to}
            onToChange={compose.setTo}
            subject={compose.subject}
            onSubjectChange={compose.setSubject}
            body={compose.body}
            onBodyChange={compose.setBody}
            canSend={compose.canSend}
            sending={compose.sending}
            error={compose.error}
            onSend={compose.handleSend}
            onClose={closeCompose}
          />
        )}
      </div>
    </div>
  );
}
