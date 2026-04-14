import { useEffect, useState } from "react";

import { getEmailContent } from "../../../api/endpoints/emails";
import { toUiError } from "../../../api/client/errors";
import type { EmailContentOut } from "../../../api/types/dto";
import type { UiError } from "../../../api/client/errors";

type Target = { account_id: string; provider_message_id: string };

type UseEmailContentReturn = {
  content: EmailContentOut | null;
  loading: boolean;
  error: UiError | null;
};

export default function useEmailContent(
  mailboxId: string,
  target: Target,
): UseEmailContentReturn {
  const [content, setContent] = useState<EmailContentOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UiError | null>(null);

  const { account_id: accountId, provider_message_id: providerMessageId } = target;

  useEffect(() => {
    let cancelled = false;

    getEmailContent(mailboxId, providerMessageId, accountId)
      .then((result) => {
        if (cancelled) return;
        setContent(result);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(toUiError(err));
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [mailboxId, accountId, providerMessageId]);

  return { content, loading, error };
}
