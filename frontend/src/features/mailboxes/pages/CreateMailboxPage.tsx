import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import useCreateMailbox from "../hooks/useCreateMailbox";
import CreateMailboxBranding from "../components/CreateMailboxBranding";
import CreateMailboxForm from "../components/CreateMailboxForm";

export default function CreateMailboxPage() {
  const navigate = useNavigate();
  const {
    displayName,
    setDisplayName,
    canSubmit,
    loading,
    error,
    createdMailbox,
    handleCreate,
  } = useCreateMailbox();

  useEffect(() => {
    if (createdMailbox) {
      navigate(`/m/${createdMailbox.mailbox_id}/accounts`, { replace: true });
    }
  }, [createdMailbox, navigate]);

  return (
    <div className="flex min-h-screen">
      <CreateMailboxBranding />
      <CreateMailboxForm
        displayName={displayName}
        onDisplayNameChange={setDisplayName}
        onSubmit={handleCreate}
        canSubmit={canSubmit}
        loading={loading}
        error={error}
      />
    </div>
  );
}
