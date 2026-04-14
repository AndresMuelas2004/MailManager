import { Navigate } from "react-router-dom";

import useMailboxGateway from "../hooks/useMailboxGateway";
import Spinner from "../../../components/common/Spinner";

export default function MailboxGatewayPage() {
  const { mailboxes } = useMailboxGateway();

  if (mailboxes === null) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (mailboxes.length > 0) {
    return <Navigate to={`/m/${mailboxes[0].mailbox_id}/accounts`} replace />;
  }

  return <Navigate to="/create-mailbox" replace />;
}
