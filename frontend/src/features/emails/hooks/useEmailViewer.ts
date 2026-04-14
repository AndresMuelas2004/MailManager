import { useCallback, useState } from "react";

import { updateReadStatus } from "../../../api/endpoints/emails";
import type { EmailMetadataOut, EmailItemRef } from "../../../api/types/dto";

function toItem(e: EmailMetadataOut): EmailItemRef {
  return { account_id: e.account_id, provider_message_id: e.provider_message_id };
}

export type UseEmailViewerReturn = {
  openedEmail: EmailMetadataOut | null;
  open: (email: EmailMetadataOut) => void;
  close: () => void;
  handleRead: (email: EmailMetadataOut) => Promise<void>;
};

export default function useEmailViewer(
  mailboxId: string,
  refresh: () => Promise<void>,
): UseEmailViewerReturn {
  const [openedEmail, setOpenedEmail] = useState<EmailMetadataOut | null>(null);

  const open = useCallback((email: EmailMetadataOut) => setOpenedEmail(email), []);
  const close = useCallback(() => setOpenedEmail(null), []);

  const handleRead = useCallback(
    async (email: EmailMetadataOut) => {
      await updateReadStatus(mailboxId, true, [toItem(email)]);
      await refresh();
    },
    [mailboxId, refresh],
  );

  return { openedEmail, open, close, handleRead };
}
