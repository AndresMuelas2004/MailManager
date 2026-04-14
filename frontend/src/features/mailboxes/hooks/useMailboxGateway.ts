import { useEffect, useState } from "react";

import { listMailboxes } from "../../../api/endpoints/mailboxes";
import type { MailboxOut } from "../../../api/types/dto";

type UseMailboxGatewayReturn = {
  mailboxes: MailboxOut[] | null;
};

export default function useMailboxGateway(): UseMailboxGatewayReturn {
  const [mailboxes, setMailboxes] = useState<MailboxOut[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMailboxes()
      .then((list) => { if (!cancelled) setMailboxes(list); })
      .catch(() => { if (!cancelled) setMailboxes([]); });
    return () => { cancelled = true; };
  }, []);

  return { mailboxes };
}
