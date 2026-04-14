import { useCallback, useEffect, useState } from "react";

import { listMailboxes, createMailbox } from "../../../api/endpoints/mailboxes";
import type { MailboxOut } from "../../../api/types/dto";

type UseMailboxListReturn = {
  mailboxes: MailboxOut[];
  currentMailboxName: string;
  handleCreate: (displayName: string) => Promise<MailboxOut | null>;
};

export default function useMailboxList(currentMailboxId: string): UseMailboxListReturn {
  const [mailboxes, setMailboxes] = useState<MailboxOut[]>([]);

  useEffect(() => {
    let cancelled = false;
    listMailboxes()
      .then((list) => { if (!cancelled) setMailboxes(list); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [currentMailboxId]);

  const currentMailbox = mailboxes.find((m) => m.mailbox_id === currentMailboxId);
  const currentMailboxName = currentMailbox?.display_name ?? "";

  const handleCreate = useCallback(async (displayName: string): Promise<MailboxOut | null> => {
    try {
      const created = await createMailbox({ display_name: displayName });
      setMailboxes((prev) => [...prev, created]);
      return created;
    } catch {
      return null;
    }
  }, []);

  return { mailboxes, currentMailboxName, handleCreate };
}
